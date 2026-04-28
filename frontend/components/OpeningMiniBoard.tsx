import clsx from "clsx";

const PIECES: Record<string, string> = {
  p: "♟",
  n: "♞",
  b: "♝",
  r: "♜",
  q: "♛",
  k: "♚",
  P: "♙",
  N: "♘",
  B: "♗",
  R: "♖",
  Q: "♕",
  K: "♔"
};

export function OpeningMiniBoard({ fen }: { fen?: string }) {
  const rows = parseFen(fen);
  return (
    <div className="mini-board">
      <div className="mini-board-grid">
        {rows.flatMap((row, rank) =>
          row.map((piece, file) => (
            <div key={`${rank}-${file}`} className={clsx("mini-board-square", (rank + file) % 2 === 0 ? "is-light" : "is-dark")}>
              {piece ? PIECES[piece] : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function parseFen(fen?: string): string[][] {
  const board = fen?.split(" ")[0] ?? "8/8/8/8/8/8/8/8";
  return board.split("/").slice(0, 8).map((rank) => {
    const row: string[] = [];
    for (const char of rank) {
      const empty = Number(char);
      if (Number.isFinite(empty) && empty > 0) {
        row.push(...Array.from({ length: empty }, () => ""));
      } else {
        row.push(char);
      }
    }
    return row.slice(0, 8);
  });
}
