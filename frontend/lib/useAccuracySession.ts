import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { reviewMove } from "./api";
import {
  summarizeSession,
  type AccuracySample,
  type AccuracySessionSummary
} from "./accuracySession";
import type { CoachHumanProfile } from "./eloAdaptation";
import type { ReviewMoveResponse } from "./types";

export type UseAccuracySessionOptions = {
  profile: CoachHumanProfile;
  elo: number;
  selectedPlanId: string | null;
};

export type UseAccuracySessionReturn = {
  samples: AccuracySample[];
  summary: AccuracySessionSummary;
  recordMove: (input: RecordMoveInput) => void;
  reset: () => void;
  inFlight: boolean;
};

export type RecordMoveInput = {
  ply: number;
  uci: string;
  san?: string;
  fenBefore: string;
  fenAfter: string;
  moveHistoryUci: string[];
};

export function useAccuracySession(options: UseAccuracySessionOptions): UseAccuracySessionReturn {
  const { profile, elo, selectedPlanId } = options;
  const [samples, setSamples] = useState<AccuracySample[]>([]);
  const [inFlight, setInFlight] = useState(false);
  const inFlightCount = useRef(0);
  const recordedPlies = useRef(new Set<number>());

  const reset = useCallback(() => {
    setSamples([]);
    setInFlight(false);
    inFlightCount.current = 0;
    recordedPlies.current = new Set();
  }, []);

  const recordMove = useCallback(
    ({ ply, uci, san, fenBefore, fenAfter, moveHistoryUci }: RecordMoveInput) => {
      if (recordedPlies.current.has(ply)) return;
      recordedPlies.current.add(ply);
      inFlightCount.current += 1;
      setInFlight(inFlightCount.current > 0);

      reviewMove({
        fenBefore,
        fenAfter,
        moveUci: uci,
        elo,
        selectedPlanId,
        moveHistoryUci
      })
        .then((response: ReviewMoveResponse) => {
          const sample: AccuracySample = {
            ply,
            uci,
            san,
            accuracy: response.accuracyPercent ?? 0,
            centipawnLoss: response.centipawnLoss ?? 0,
            quality: response.quality
          };
          setSamples((prev) => {
            if (prev.some((existing) => existing.ply === ply)) return prev;
            const next = [...prev, sample];
            next.sort((a, b) => a.ply - b.ply);
            return next;
          });
        })
        .catch(() => {
          recordedPlies.current.delete(ply);
        })
        .finally(() => {
          inFlightCount.current = Math.max(0, inFlightCount.current - 1);
          setInFlight(inFlightCount.current > 0);
        });
    },
    [elo, selectedPlanId]
  );

  useEffect(() => {
    return () => {
      recordedPlies.current.clear();
    };
  }, []);

  const summary = useMemo(() => summarizeSession(samples, profile), [samples, profile]);

  return { samples, summary, recordMove, reset, inFlight };
}
