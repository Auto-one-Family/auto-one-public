/**
 * Finds the first free position in a grid for a widget of given width/height.
 * Scans the grid row by row from top-left to bottom-right.
 */
export function findFirstFreePosition(
  widgets: Array<{ x: number; y: number; w: number; h: number }>,
  newW: number,
  newH: number,
  columns: number = 12
): { x: number; y: number } {
  let maxRow = 0
  for (const widget of widgets) {
    const bottom = (widget.y ?? 0) + (widget.h ?? 1)
    if (bottom > maxRow) maxRow = bottom
  }
  maxRow += newH + 2

  const occupied = new Set<string>()
  for (const widget of widgets) {
    const wx = widget.x ?? 0
    const wy = widget.y ?? 0
    const ww = widget.w ?? 1
    const wh = widget.h ?? 1
    for (let row = wy; row < wy + wh; row++) {
      for (let col = wx; col < wx + ww; col++) {
        occupied.add(`${col},${row}`)
      }
    }
  }

  for (let row = 0; row < maxRow; row++) {
    for (let col = 0; col <= columns - newW; col++) {
      let fits = true
      for (let r = row; r < row + newH && fits; r++) {
        for (let c = col; c < col + newW && fits; c++) {
          if (occupied.has(`${c},${r}`)) {
            fits = false
          }
        }
      }
      if (fits) {
        return { x: col, y: row }
      }
    }
  }

  return { x: 0, y: maxRow }
}
