import { useMemo, useRef, useState, useEffect, type ReactNode } from 'react';

interface VirtualListProps<T> {
  items: T[];
  /** Height in px of each row (fixed per row, may differ between rows). */
  rowHeight: (item: T, index: number) => number;
  renderRow: (item: T, index: number) => ReactNode;
  rowKey: (item: T, index: number) => string;
  /** Maximum height of the scroll viewport in px. */
  maxHeight: number;
  /** Called when the user scrolls within `endThreshold` px of the end. */
  onEndReached?: () => void;
  endThreshold?: number;
  overscan?: number;
  className?: string;
}

/**
 * Renders only the rows in (or near) the viewport, so lists of tens of thousands of
 * files or functions cost a few dozen DOM nodes instead of hundreds of thousands.
 */
export default function VirtualList<T>({
  items, rowHeight, renderRow, rowKey, maxHeight, onEndReached,
  endThreshold = 400, overscan = 8, className = '',
}: VirtualListProps<T>) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  // offsets[i] = top of row i; offsets[n] = total height
  const offsets = useMemo(() => {
    const out = new Array<number>(items.length + 1);
    out[0] = 0;
    for (let i = 0; i < items.length; i++) out[i + 1] = out[i] + rowHeight(items[i], i);
    return out;
  }, [items, rowHeight]);
  const total = offsets[items.length];
  const viewport = Math.min(maxHeight, total);

  // A new (shorter) list: keep the scroll position inside it.
  useEffect(() => {
    if (ref.current && ref.current.scrollTop > total) {
      ref.current.scrollTop = 0;
      setScrollTop(0);
    }
  }, [total]);

  const firstAt = (y: number) => {
    let lo = 0, hi = items.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (offsets[mid] <= y) lo = mid; else hi = mid - 1;
    }
    return lo;
  };
  const start = items.length ? Math.max(0, firstAt(scrollTop) - overscan) : 0;
  let end = start;
  while (end < items.length && offsets[end] < scrollTop + maxHeight) end++;
  end = Math.min(items.length, end + overscan);

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    setScrollTop(el.scrollTop);
    if (onEndReached && el.scrollTop + el.clientHeight >= total - endThreshold) onEndReached();
  };

  return (
    <div ref={ref} onScroll={onScroll} className={`overflow-y-auto ${className}`} style={{ height: viewport }}>
      <div style={{ height: total, position: 'relative' }}>
        {items.slice(start, end).map((item, i) => {
          const index = start + i;
          return (
            <div
              key={rowKey(item, index)}
              style={{ position: 'absolute', top: offsets[index], left: 0, right: 0, height: offsets[index + 1] - offsets[index] }}
            >
              {renderRow(item, index)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
