import { useCallback, useState } from "react";

/**
 * Hover and keyboard-focus tooltips for chart marks.
 * Spread tip.bind(content) onto a mark, and render <Tip tip={tip.tip} /> once nearby.
 * A tooltip only repeats values that are also visible as labels or in a table.
 */
export function useTip() {
  const [tip, setTip] = useState(null);
  const hide = useCallback(() => setTip(null), []);
  const bind = (content) => ({
    onPointerEnter: (e) => setTip({ x: e.clientX, y: e.clientY, content }),
    onPointerMove: (e) => setTip({ x: e.clientX, y: e.clientY, content }),
    onPointerLeave: hide,
    onFocus: (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      setTip({ x: r.left + r.width / 2, y: r.top + r.height / 2, content });
    },
    onBlur: hide,
  });
  return { tip, bind, hide };
}

const WIDTH = 280;

export function Tip({ tip }) {
  if (!tip) return null;
  const left = Math.max(8, Math.min(tip.x + 14, window.innerWidth - WIDTH - 8));
  const roomBelow = tip.y < window.innerHeight - 180;
  const place = roomBelow ? { top: tip.y + 18 } : { bottom: window.innerHeight - tip.y + 12 };
  return (
    <div className="tip" role="tooltip" style={{ left, maxWidth: WIDTH, ...place }}>
      {tip.content}
    </div>
  );
}
