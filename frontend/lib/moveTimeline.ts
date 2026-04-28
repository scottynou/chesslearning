export type MoveSource = "manual" | "bot";

export type TimelineMove = {
  moveUci: string;
  source: MoveSource;
};

export type UndoTimelineResult = {
  historyUci: string[];
  moveSources: MoveSource[];
  redoStack: TimelineMove[];
  undoneMove: TimelineMove | null;
};

export function canStepBack(historyLength: number, protectedPlyCount = 0) {
  return historyLength > protectedPlyCount;
}

export function undoTimeline(
  historyUci: string[],
  moveSources: MoveSource[],
  redoStack: TimelineMove[],
  protectedPlyCount = 0
): UndoTimelineResult {
  if (!canStepBack(historyUci.length, protectedPlyCount)) {
    return { historyUci, moveSources, redoStack, undoneMove: null };
  }

  const undoneIndex = historyUci.length - 1;
  const undoneMove = {
    moveUci: historyUci[undoneIndex],
    source: moveSources[undoneIndex] ?? "manual"
  };

  return {
    historyUci: historyUci.slice(0, -1),
    moveSources: moveSources.slice(0, -1),
    redoStack: [undoneMove, ...redoStack],
    undoneMove
  };
}

export function redoTimeline(redoStack: TimelineMove[]) {
  const [nextMove, ...remainingRedoStack] = redoStack;
  return {
    nextMove: nextMove ?? null,
    redoStack: remainingRedoStack
  };
}
