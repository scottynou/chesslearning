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
    <div className="aspect-square overflow-hidden rounded border border-line bg-white shadow-sm">
      <div className="grid h-full grid-cols-8 grid-rows-8">
        {rows.flatMap((row, rank) =>
          row.map((piece, file) => (
            <div
              key={`${rank}-${file}`}
              className={clsx(
                "grid place-items-center text-[0.7rem] sm:text-xs",
                (rank + file) % 2 === 0 ? "bg-stone-100" : "bg-sage/25"
              )}
            >
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
