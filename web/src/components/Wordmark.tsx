/** The header lockup: the mark, then PURSER in the display serif.
 *  The mark is the raster asset cropped by scripts/make_icons.py -- it is not
 *  redrawn as SVG, because hand-tracing the crescent and the wing would drift
 *  from the artwork the brand actually uses. */
export function Wordmark() {
  return (
    <span className="wordmark">
      <img src="/icons/icon-32.png" alt="" width={27} height={27} />
      <span className="wordmark-text">PURSER</span>
    </span>
  );
}
