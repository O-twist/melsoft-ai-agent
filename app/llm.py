"""LLM access. One interface, three backends: Gemini and OpenRouter over REST (no SDK), and an offline mock.

Every backend has call() for text and call_vision() for text with photos (the Clerk reading handwritten pages).

With both keys set, Gemini is used first and OpenRouter takes over for the rest of the run if Gemini is
busy, unreachable or refuses the request. If no live model can answer, the offline mock finishes the run
(see Fallback).
"""
import base64
import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from . import mock

API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash"
OPENROUTER_API = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openrouter/free"  # OpenRouter's own router: picks a free model that is up


class LLMError(Exception):
    pass


class Busy(LLMError):
    """The service is overloaded, rate-limited or unreachable, and waiting did not help."""


def parse_json(text):
    """Parse JSON out of a model reply, tolerating code fences and stray prose."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


class Gemini:
    name = "gemini"

    def __init__(self, key, model=None):
        self.key = key
        self.api = os.getenv("GEMINI_API_BASE", API).rstrip("/")
        self.model = model or os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
        # Free-tier keys are limited per minute, so calls are spaced out.
        self.min_gap = float(os.getenv("GEMINI_MIN_GAP", "4"))
        self.delays = [5, 15, 30, 60]  # waits between retries when Gemini is busy or unreachable
        self.calls = 0
        self._last = 0.0
        self._lock = threading.Lock()
        self._model_checked = False
        # Request settings, richest first. If Gemini rejects one (HTTP 400) the next, simpler one is used.
        json_only = {"responseMimeType": "application/json"}
        thinking = os.getenv("GEMINI_THINKING", "low").strip().upper()
        self._settings = ([{**json_only, "thinkingConfig": {"thinkingLevel": thinking}}] if thinking else []) + [json_only, None]

    def _http(self, method, path, body=None):
        req = urllib.request.Request(
            f"{self.api}/{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode())

    def _body(self, system, prompt, images=None):
        parts = [{"text": prompt}] + [
            {"inline_data": {"mime_type": im["mime"], "data": base64.b64encode(im["data"]).decode("ascii")}}
            for im in images or []]
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
        }
        if self._settings[0]:
            body["generationConfig"] = self._settings[0]
        return body

    @staticmethod
    def _text(out):
        cands = out.get("candidates") or []
        if not cands:
            raise LLMError(f"Gemini returned no answer ({out.get('promptFeedback') or 'no reason given'}).")
        parts = (cands[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    @staticmethod
    def _detail(err):
        """The human-readable part of an HTTP error from Gemini."""
        raw = err.read().decode(errors="replace")
        try:
            return str(json.loads(raw)["error"]["message"])[:300]
        except (ValueError, KeyError, TypeError):
            return raw[:300]

    def _pick_model(self):
        """The configured model is not available to this key: choose the newest plain Flash model instead."""
        models, token = [], ""
        for _ in range(5):
            page = self._http("GET", "models?pageSize=200" + (f"&pageToken={token}" if token else ""))
            models += page.get("models", [])
            token = page.get("nextPageToken")
            if not token:
                break
        names = [m.get("name", "").split("/", 1)[-1] for m in models
                 if "generateContent" in m.get("supportedGenerationMethods", ["generateContent"])]
        names = [n for n in names if n and n != self.model]

        def newest(pattern):
            found = []
            for n in names:
                m = re.fullmatch(pattern, n)
                if m:
                    found.append((tuple(int(x) for x in m.group(1).split(".")), n))
            return max(found)[1] if found else None

        version = r"(\d+(?:\.\d+)*)"
        choice = (newest(rf"gemini-{version}-flash")
                  or ("gemini-flash-latest" if "gemini-flash-latest" in names else None)
                  or newest(rf"gemini-{version}-flash-lite"))
        if not choice:
            raise LLMError(f"Model '{self.model}' is not available to this API key, and no Flash model was found "
                           "to use instead. Set GEMINI_MODEL in .env to a model your key can use.")
        return choice

    def call(self, task, system, prompt, data=None, log=None):
        """Return the model's reply as parsed JSON. `data` is only used by the mock backend."""
        return self._ask(task, system, prompt, None, log)

    def call_vision(self, task, system, prompt, images, data=None, log=None):
        """The same, with photos sent alongside the prompt as inline_data. images: [{mime, data (bytes)}]."""
        return self._ask(task, system, prompt, images, log)

    def _ask(self, task, system, prompt, images, log):
        say = log or (lambda msg: None)
        retries = bad_json = 0

        def wait_and_retry(why, pause=None):
            nonlocal retries
            if retries >= len(self.delays):
                return False
            pause = max(self.delays[retries], pause or 0)
            say(f"{why} Retrying in {round(pause)}s.")
            time.sleep(pause)
            retries += 1
            return True

        while True:
            with self._lock:  # one request at a time, spaced out
                gap = self.min_gap - (time.time() - self._last)
                if gap > 0:
                    time.sleep(gap)
                self._last = time.time()
                self.calls += 1
            try:
                out = self._http("POST", f"models/{self.model}:generateContent", self._body(system, prompt, images))
                return parse_json(self._text(out))
            except json.JSONDecodeError:
                bad_json += 1
                if bad_json > 2:
                    raise LLMError(f"Gemini did not return valid JSON for the '{task}' step.")
                say(f"The reply for the '{task}' step was not valid JSON. Asking again.")
            except urllib.error.HTTPError as e:
                detail = self._detail(e)
                bad_key = "api key" in detail.lower() or e.code in (401, 403)
                if e.code == 404 and not self._model_checked:
                    self._model_checked = True
                    old, self.model = self.model, self._pick_model()
                    say(f"Model '{old}' is not available to this key. Switched to '{self.model}'.")
                    continue
                if e.code == 400 and not bad_key and len(self._settings) > 1:
                    self._settings.pop(0)
                    say("Gemini rejected a request setting. Trying again with simpler settings.")
                    continue
                if e.code in (429, 500, 502, 503, 504):
                    hint = re.search(r"retry in ([\d.]+)\s*s", detail, re.I)
                    if wait_and_retry(f"Gemini is busy (HTTP {e.code}).", min(90, float(hint.group(1)) + 1) if hint else None):
                        continue
                    raise Busy(f"Gemini HTTP {e.code}: {detail}")
                if bad_key:
                    raise LLMError(f"Gemini refused the API key (HTTP {e.code}). Check GEMINI_API_KEY in .env. {detail}")
                raise LLMError(f"Gemini HTTP {e.code}: {detail}")
            except (OSError, http.client.HTTPException) as e:  # no connection, DNS failure, timeout, dropped reply
                reason = getattr(e, "reason", None) or e
                if not wait_and_retry(f"Network problem ({reason})."):
                    raise Busy(f"Cannot reach Gemini: {reason}")


class _Reported(Exception):
    """An error OpenRouter put inside an otherwise successful reply."""

    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


class OpenRouter:
    """OpenRouter's OpenAI-style chat API. One key reaches many models, including free ones."""
    name = "openrouter"

    def __init__(self, key, model=None):
        self.key = key
        self.api = os.getenv("OPENROUTER_API_BASE", OPENROUTER_API).rstrip("/")
        self.model = model or os.getenv("OPENROUTER_MODEL", "").strip() or OPENROUTER_MODEL
        # Reading photos needs a model that takes images. The free router picks one when asked; this can name one instead.
        self.vision_model = os.getenv("OPENROUTER_VISION_MODEL", "").strip() or self.model
        self.served = None  # the model that actually answered, when the router picks one
        self.min_gap = float(os.getenv("OPENROUTER_MIN_GAP", "3"))  # free models allow about 20 requests a minute
        self.delays = [5, 15, 30, 60]
        self.calls = 0
        self._last = 0.0
        self._lock = threading.Lock()
        # Ask for JSON-only replies. A model that does not support that setting gets the plain request instead.
        self._settings = [{"response_format": {"type": "json_object"}}, {}]

    def _http(self, body):
        req = urllib.request.Request(
            f"{self.api}/chat/completions", data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                     "X-Title": "Marking Colleague"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def _detail(err):
        raw = err.read().decode(errors="replace")
        try:
            return str(json.loads(raw)["error"]["message"])[:300]
        except (ValueError, KeyError, TypeError):
            return raw[:300]

    def call(self, task, system, prompt, data=None, log=None):
        """Return the model's reply as parsed JSON. `data` is only used by the mock backend."""
        return self._ask(task, system, prompt, None, log)

    def call_vision(self, task, system, prompt, images, data=None, log=None):
        """The same, with photos sent as image_url parts. images: [{mime, data (bytes)}]."""
        return self._ask(task, system, prompt, images, log)

    def _ask(self, task, system, prompt, images, log):
        say = log or (lambda msg: None)
        retries = bad_json = 0
        model = self.vision_model if images else self.model
        user = prompt if not images else [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": f"data:{im['mime']};base64,{base64.b64encode(im['data']).decode('ascii')}"}}
            for im in images]

        def wait_and_retry(why):
            nonlocal retries
            if retries >= len(self.delays):
                return False
            say(f"{why} Retrying in {self.delays[retries]}s.")
            time.sleep(self.delays[retries])
            retries += 1
            return True

        while True:
            with self._lock:
                gap = self.min_gap - (time.time() - self._last)
                if gap > 0:
                    time.sleep(gap)
                self._last = time.time()
                self.calls += 1
            body = {"model": model, **self._settings[0],
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            try:
                out = self._http(body)
                if out.get("error"):  # an upstream model failed, reported inside a 200 reply
                    err = out["error"]
                    code = err.get("code")
                    raise _Reported(code if isinstance(code, int) else 502, str(err.get("message"))[:300])
                choice = (out.get("choices") or [{}])[0]
                self.served = out.get("model") or self.served
                return parse_json((choice.get("message") or {}).get("content") or "")
            except json.JSONDecodeError:
                bad_json += 1
                if bad_json > 2:
                    raise LLMError(f"OpenRouter ({self.served or self.model}) did not return valid JSON for the '{task}' step.")
                say(f"The reply for the '{task}' step was not valid JSON. Asking again.")
            except (urllib.error.HTTPError, _Reported) as e:
                detail = e.detail if isinstance(e, _Reported) else self._detail(e)
                if e.code in (401, 403):
                    raise LLMError(f"OpenRouter refused the API key (HTTP {e.code}). Check OPENROUTER_API_KEY in .env. {detail}")
                if e.code == 402:
                    raise LLMError(f"OpenRouter says this key has no credit left for '{self.model}' (HTTP 402). "
                                   f"Set OPENROUTER_MODEL to a free model. {detail}")
                if e.code == 400 and len(self._settings) > 1:
                    self._settings.pop(0)
                    say("OpenRouter rejected a request setting. Trying again with simpler settings.")
                    continue
                if e.code == 429 and "per-day" in detail.lower():  # the free daily allowance is used up: waiting will not help
                    raise Busy(f"OpenRouter's daily free limit is used up (HTTP 429). {detail}")
                if e.code in (408, 429, 500, 502, 503, 504):
                    if wait_and_retry(f"OpenRouter is busy (HTTP {e.code})."):
                        continue
                    raise Busy(f"OpenRouter HTTP {e.code}: {detail}")
                raise LLMError(f"OpenRouter HTTP {e.code}: {detail}")
            except (OSError, http.client.HTTPException) as e:
                reason = getattr(e, "reason", None) or e
                if not wait_and_retry(f"Network problem ({reason})."):
                    raise Busy(f"Cannot reach OpenRouter: {reason}")


SERVICE = {"gemini": "Gemini", "openrouter": "OpenRouter", "mock": "the offline demo marker"}


class Fallback:
    """A chain of backends, tried in order: Gemini, then OpenRouter, then the offline demo marker.

    When the one answering fails (busy, unreachable, key refused, no valid reply), the next takes over for the
    rest of the run, so a run is never lost to a model that cannot answer. Each run gets a fresh Fallback, so
    the next run tries the first backend again.

    deadline: seconds a run may spend on live models. Once it has passed, the offline demo marker at the end
    of the chain finishes the run. This keeps a run inside a serverless time limit. 0 means no limit.
    """

    def __init__(self, primary, *others, deadline=None):
        self.chain = [primary, *others]
        self.primary, self.backup = primary, (others[0] if others else None)
        for backend in self.chain[:-1]:  # with a backup ready, do not wait minutes for a busy service
            if hasattr(backend, "delays"):
                backend.delays = backend.delays[:2]
        self.active = primary
        self.switched = None  # why the next backend took over, once it has
        self.deadline = float(os.getenv("LLM_DEADLINE", "0") or 0) if deadline is None else deadline
        self._started = None

    @property
    def name(self):
        return self.active.name

    @property
    def model(self):
        return self.active.model

    @property
    def calls(self):
        return sum(backend.calls for backend in self.chain)

    @property
    def served(self):
        """The model OpenRouter's router picked for the last request, once OpenRouter has taken over."""
        return getattr(self.active, "served", None)

    @property
    def standby(self):
        """The live model waiting to take over, while the one before it is still answering."""
        following = self._next()
        return following.model if following is not None and following.name != "mock" else None

    def _next(self):
        at = self.chain.index(self.active)
        return self.chain[at + 1] if at + 1 < len(self.chain) else None

    def call(self, task, system, prompt, data=None, log=None):
        return self._route("call", task, system, prompt, data=data, log=log)

    def call_vision(self, task, system, prompt, images, data=None, log=None):
        return self._route("call_vision", task, system, prompt, images, data=data, log=log)

    def _switch(self, to, why, say):
        was = SERVICE.get(self.active.name, self.active.name)
        self.active, self.switched = to, why
        target = SERVICE.get(to.name, to.name) + ("" if to.name == "mock" else f" ({to.model})")
        say(f"{was} could not answer ({why}). Switching to {target} for the rest of this run.")

    def _route(self, method, *args, **kw):
        say = kw.get("log") or (lambda msg: None)
        if self._started is None:
            self._started = time.time()
        last = self.chain[-1]
        if (self.deadline and self.active is not last and last.name == "mock"
                and time.time() - self._started > self.deadline):
            self._switch(last, f"the live models have had their {round(self.deadline)} seconds for this run", say)
        while True:
            try:
                return getattr(self.active, method)(*args, **kw)
            except LLMError as e:
                following = self._next()
                if following is None:
                    raise
                self._switch(following, str(e), say)


class Mock:
    """Offline stand-in that marks with simple text heuristics. For tests and as a demo fallback."""
    name = "mock"
    model = "offline heuristics"

    def __init__(self):
        self.calls = 0
        self.delay = float(os.getenv("MOCK_DELAY", "0.7"))

    def call(self, task, system, prompt, data=None, log=None):
        self.calls += 1
        time.sleep(self.delay)
        return mock.respond(task, data or {})

    def call_vision(self, task, system, prompt, images, data=None, log=None):
        """The mock cannot see: it recognises the sample pages by the hash in `data` (see mock.read_page)."""
        return self.call(task, system, prompt, data, log)


def make_llm():
    """Gemini, OpenRouter, or both (Gemini first), depending on which keys are in .env. Neither: the offline mock.

    Whenever a live model is used, the offline mock stands behind it, so a run finishes even if every model fails.
    """
    if os.getenv("MOCK", "") == "1":
        return Mock()
    gemini, openrouter = os.getenv("GEMINI_API_KEY", "").strip(), os.getenv("OPENROUTER_API_KEY", "").strip()
    live = ([Gemini(gemini)] if gemini else []) + ([OpenRouter(openrouter)] if openrouter else [])
    return Fallback(*live, Mock()) if live else Mock()
