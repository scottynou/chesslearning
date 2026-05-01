"use client";

import type { ChangeEvent, ReactNode, TouchEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import { ChevronLeft, ChevronRight, ImageUp, Menu, X } from "lucide-react";
import { ChessCoachBoard } from "@/components/ChessCoachBoard";
import { GameControls } from "@/components/GameControls";
import { MoveHistory } from "@/components/MoveHistory";
import { OpeningRepertoirePanel } from "@/components/OpeningRepertoirePanel";
import { PlanFirstPanel } from "@/components/PlanFirstPanel";
import { SideSelectionPanel } from "@/components/SideSelectionPanel";
import { getPlanRecommendations, importPositionImage, listAvailablePlans, requestBotMove } from "@/lib/api";
import { canMoveInMode, gameStatus, isPromotionAttempt, tryMove } from "@/lib/chess";
import {
  DEFAULT_HUMAN_PROFILE,
  HUMAN_PROFILE_SETTINGS,
  applyAdaptiveSignal,
  baseEloForProfile,
  effectiveElo,
  freshEloTrendState,
  normalizeHumanProfile,
  skillLevelForElo,
  type CoachHumanProfile
} from "@/lib/eloAdaptation";
import { canStepBack, redoTimeline, undoTimeline, type MoveSource, type TimelineMove } from "@/lib/moveTimeline";
import type { ImportPositionImageResponse, Orientation, PlanRecommendationsResponse, PlayMode, StrategyPlan } from "@/lib/types";

type PendingPromotion = {
  from: string;
  to: string;
};

type EditablePiece = "K" | "Q" | "R" | "B" | "N" | "P" | "k" | "q" | "r" | "b" | "n" | "p";
type EditableBoard = Record<string, EditablePiece | null>;
type ImageImportStatus = "loading" | "local" | "ready" | "manual";

type ImageImportDraft = {
  previewUrl: string;
  boardReferenceUrl: string | null;
  result: ImportPositionImageResponse | null;
  boardMap: EditableBoard;
  sideToMove: "white" | "black";
  userSide: "white" | "black";
  humanProfile: CoachHumanProfile;
  boardOrientation: "white_bottom" | "black_bottom" | "unknown";
  status: ImageImportStatus;
  message: string | null;
  confidence: number | null;
  warnings: string[];
};

type PreparedImageVariant = {
  imageData: string;
  mimeType: string;
  label: string;
  dataUrl?: string;
};

type LocalSquareDetection = {
  square: string;
  piece: EditablePiece | null;
  confidence: number;
  occupied: boolean;
};

type LocalBoardDetection = {
  boardMap: EditableBoard;
  confidence: number;
  warnings: string[];
  referenceUrl: string;
};

type EloChange = {
  id: number;
  previous: number;
  current: number;
  delta: number;
};

type VerboseMove = Move & {
  before?: string;
  after?: string;
};

type AppStage = "side-selection" | "white-plan-selection" | "black-first-move" | "black-plan-selection" | "coach";
type UserSide = "white" | "black" | "both";
type NavigationSnapshot = {
  key: "chess-learning-navigation";
  appStage: AppStage;
  userSide: UserSide;
  orientation: Orientation;
  mode: PlayMode;
  humanProfile: CoachHumanProfile;
  selectedPlanId: string | null;
  firstOpponentMove: string | null;
  historyUci: string[];
  importedFen: string | null;
};

const INTERNAL_MAX_MOVES = 4;
const INTERNAL_ENGINE_DEPTH = 6;
const BOT_ENGINE_DEPTH = 14;
const NAVIGATION_KEY = "chess-learning-navigation";
const PLAYER_RECOMMENDATION_ARROW = "rgba(224,185,118,0.82)";
const OPPONENT_EXPECTED_ARROW = "rgba(239,118,118,0.78)";
const IMAGE_IMPORT_MAX_SOURCE_BYTES = 24 * 1024 * 1024;
const IMAGE_IMPORT_TARGET_BYTES = 1.4 * 1024 * 1024;
const IMAGE_IMPORT_MAX_PAYLOAD_CHARS = 2.4 * 1024 * 1024;
const IMAGE_IMPORT_DIMENSIONS = [1400, 1100, 900, 720];
const IMAGE_IMPORT_QUALITIES = [0.82, 0.7, 0.58, 0.46];
const LOCAL_IMAGE_IMPORT_CANVAS_SIZE = 640;
const LOCAL_TEMPLATE_SIZE = 18;
const EDITABLE_FILES = ["a", "b", "c", "d", "e", "f", "g", "h"] as const;
const EDITABLE_RANKS = ["8", "7", "6", "5", "4", "3", "2", "1"] as const;
const EDITABLE_PIECES: Array<{ value: EditablePiece | null; label: string; symbol: string }> = [
  { value: null, label: "Effacer", symbol: "Vide" },
  { value: "K", label: "Roi blanc", symbol: "♔" },
  { value: "Q", label: "Dame blanche", symbol: "♕" },
  { value: "R", label: "Tour blanche", symbol: "♖" },
  { value: "B", label: "Fou blanc", symbol: "♗" },
  { value: "N", label: "Cavalier blanc", symbol: "♘" },
  { value: "P", label: "Pion blanc", symbol: "♙" },
  { value: "k", label: "Roi noir", symbol: "♚" },
  { value: "q", label: "Dame noire", symbol: "♛" },
  { value: "r", label: "Tour noire", symbol: "♜" },
  { value: "b", label: "Fou noir", symbol: "♝" },
  { value: "n", label: "Cavalier noir", symbol: "♞" },
  { value: "p", label: "Pion noir", symbol: "♟" }
];
const LOCAL_TEMPLATE_SYMBOLS: Record<Lowercase<EditablePiece>, string> = {
  k: "\u265A",
  q: "\u265B",
  r: "\u265C",
  b: "\u265D",
  n: "\u265E",
  p: "\u265F"
};

function buildGameFromHistory(moves: string[], startFen?: string | null) {
  const next = startFen ? new Chess(startFen) : new Chess();
  for (const move of moves) {
    try {
      next.move({
        from: move.slice(0, 2),
        to: move.slice(2, 4),
        ...(move.slice(4) ? { promotion: move.slice(4) } : {})
      });
    } catch {
      break;
    }
  }
  return next;
}

function historyFromGame(game: Chess) {
  return (game.history({ verbose: true }) as VerboseMove[]).map((move) => `${move.from}${move.to}${move.promotion ?? ""}`);
}

function isUciMove(value: string) {
  return /^[a-h][1-8][a-h][1-8][qrbn]?$/.test(value);
}

function parseHistoryParam(params: URLSearchParams, fallbackFirstMove: string | null) {
  const movesParam = params.get("moves");
  if (movesParam !== null) {
    return movesParam
      .split(/[,\s]+/)
      .map((move) => move.trim())
      .filter(isUciMove);
  }

  return fallbackFirstMove && isUciMove(fallbackFirstMove) ? [fallbackFirstMove] : [];
}

function isNavigationSnapshot(value: unknown): value is NavigationSnapshot {
  return Boolean(value && typeof value === "object" && (value as NavigationSnapshot).key === NAVIGATION_KEY);
}

function snapshotFromLocation(): NavigationSnapshot {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  const sideParam = params.get("side");
  const userSide: UserSide = sideParam === "black" || sideParam === "both" ? sideParam : "white";
  const plan = params.get("plan");
  const firstParam = params.get("first");
  const first = firstParam && isUciMove(firstParam) ? firstParam : null;
  const historyMoves = parseHistoryParam(params, first);
  const humanProfile = normalizeHumanProfile(params.get("profile"));

  if (view === "white-plans") {
    return createNavigationSnapshot({ appStage: "white-plan-selection", userSide: "white", orientation: "white", humanProfile });
  }
  if (view === "black-first-move") {
    return createNavigationSnapshot({ appStage: "black-first-move", userSide: "black", orientation: "black", humanProfile });
  }
  if (view === "black-plans") {
    return createNavigationSnapshot({
      appStage: "black-plan-selection",
      userSide: "black",
      orientation: "black",
      humanProfile,
      firstOpponentMove: first,
      historyUci: historyMoves
    });
  }
  if (view === "coach" || view === "plan-intro") {
    return createNavigationSnapshot({
      appStage: "coach",
      userSide,
      orientation: userSide === "black" ? "black" : "white",
      humanProfile,
      selectedPlanId: plan,
      firstOpponentMove: first,
      historyUci: historyMoves
    });
  }
  return createNavigationSnapshot();
}

function createNavigationSnapshot(overrides: Partial<NavigationSnapshot> = {}): NavigationSnapshot {
  return {
    key: NAVIGATION_KEY,
    appStage: "side-selection",
    userSide: "white",
    orientation: "white",
    mode: "both",
    humanProfile: DEFAULT_HUMAN_PROFILE,
    selectedPlanId: null,
    firstOpponentMove: null,
    historyUci: [],
    importedFen: null,
    ...overrides
  };
}

function dataUrlToBase64(dataUrl: string) {
  const commaIndex = dataUrl.indexOf(",");
  const encoded = commaIndex >= 0 ? dataUrl.slice(commaIndex + 1) : dataUrl;
  if (encoded.length > IMAGE_IMPORT_MAX_PAYLOAD_CHARS) {
    throw new Error("Image trop lourde apres compression. Recadre le plateau puis reessaie.");
  }
  return encoded;
}

function fenWithSideToMove(fen: string, sideToMove: "white" | "black") {
  const parts = fen.split(" ");
  if (parts.length < 6) return fen;
  parts[1] = sideToMove === "white" ? "w" : "b";
  return parts.join(" ");
}

function normalizeFenInput(input: string) {
  const cleaned = input
    .replace(/```(?:text|fen)?/gi, " ")
    .replace(/```/g, " ")
    .replace(/^fen\s*[:=]\s*/i, "")
    .trim()
    .split(/\s+/)
    .join(" ");
  const placementMatch = cleaned.match(/[pnbrqkPNBRQK1-8]+(?:\/[pnbrqkPNBRQK1-8]+){7}(?:\s+[wb](?:\s+(?:K?Q?k?q?|-)(?:\s+(?:-|[a-h][36])(?:\s+\d+\s+\d+)?)?)?)?/);
  const candidate = placementMatch?.[0]?.trim() ?? cleaned;
  const parts = candidate.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return `${parts[0]} w - - 0 1`;
  if (parts.length === 2) return `${parts[0]} ${parts[1]} - - 0 1`;
  if (parts.length === 3) return `${parts[0]} ${parts[1]} ${parts[2]} - 0 1`;
  if (parts.length === 4) return `${parts[0]} ${parts[1]} ${parts[2]} ${parts[3]} 0 1`;
  return parts.slice(0, 6).join(" ");
}

function emptyEditableBoard(): EditableBoard {
  const board: EditableBoard = {};
  for (const rank of EDITABLE_RANKS) {
    for (const file of EDITABLE_FILES) {
      board[`${file}${rank}`] = null;
    }
  }
  return board;
}

function editableBoardFromFen(fen: string): EditableBoard {
  const board = emptyEditableBoard();
  const placement = fen.split(" ")[0] || "8/8/8/8/8/8/8/8";
  const rows = placement.split("/");
  rows.forEach((row, rowIndex) => {
    const rank = String(8 - rowIndex);
    let fileIndex = 0;
    for (const char of row) {
      const emptyCount = Number(char);
      if (Number.isInteger(emptyCount) && emptyCount > 0) {
        fileIndex += emptyCount;
        continue;
      }
      const file = EDITABLE_FILES[fileIndex];
      if (file && isEditablePiece(char)) {
        board[`${file}${rank}`] = char;
      }
      fileIndex += 1;
    }
  });
  return board;
}

function editableBoardToFen(board: EditableBoard, sideToMove: "white" | "black") {
  const rows = EDITABLE_RANKS.map((rank) => {
    let row = "";
    let empty = 0;
    for (const file of EDITABLE_FILES) {
      const piece = board[`${file}${rank}`];
      if (!piece) {
        empty += 1;
      } else {
        if (empty) row += String(empty);
        row += piece;
        empty = 0;
      }
    }
    if (empty) row += String(empty);
    return row || "8";
  });
  return `${rows.join("/")} ${sideToMove === "white" ? "w" : "b"} - - 0 1`;
}

function editableBoardIsValid(board: EditableBoard, sideToMove: "white" | "black") {
  try {
    new Chess(editableBoardToFen(board, sideToMove));
    return true;
  } catch {
    return false;
  }
}

function isEditablePiece(value: string): value is EditablePiece {
  return ["K", "Q", "R", "B", "N", "P", "k", "q", "r", "b", "n", "p"].includes(value);
}

function rotateEditableBoard(board: EditableBoard): EditableBoard {
  const rotated = emptyEditableBoard();
  for (const [square, piece] of Object.entries(board)) {
    if (!piece) continue;
    const fileIndex = EDITABLE_FILES.indexOf(square[0] as (typeof EDITABLE_FILES)[number]);
    const rankIndex = EDITABLE_RANKS.indexOf(square[1] as (typeof EDITABLE_RANKS)[number]);
    if (fileIndex < 0 || rankIndex < 0) continue;
    const nextFile = EDITABLE_FILES[7 - fileIndex];
    const nextRank = EDITABLE_RANKS[7 - rankIndex];
    rotated[`${nextFile}${nextRank}`] = piece;
  }
  return rotated;
}

function pieceSymbol(piece: EditablePiece | null) {
  if (!piece) return "";
  return EDITABLE_PIECES.find((item) => item.value === piece)?.symbol ?? "";
}

function pieceLabel(piece: EditablePiece | null) {
  return EDITABLE_PIECES.find((item) => item.value === piece)?.label ?? "Effacer";
}

function orientedEditableSquares(orientation: Orientation) {
  const files = orientation === "black" ? [...EDITABLE_FILES].reverse() : [...EDITABLE_FILES];
  const ranks = orientation === "black" ? [...EDITABLE_RANKS].reverse() : [...EDITABLE_RANKS];
  return ranks.flatMap((rank) => files.map((file) => `${file}${rank}`));
}

function boardOrientationFromOrientation(value: Orientation): ImageImportDraft["boardOrientation"] {
  return value === "black" ? "black_bottom" : "white_bottom";
}

function orientationFromBoardOrientation(value: ImageImportDraft["boardOrientation"]): Orientation {
  return value === "black_bottom" ? "black" : "white";
}

function sideToMoveFromFen(fen: string): "white" | "black" {
  return fen.split(" ")[1] === "b" ? "black" : "white";
}

function createImageImportDraft(params: {
  previewUrl: string;
  fen: string;
  sideToMove?: "white" | "black";
  userSide: "white" | "black";
  humanProfile: CoachHumanProfile;
  boardOrientation: ImageImportDraft["boardOrientation"];
  status: ImageImportStatus;
  message?: string | null;
  confidence?: number | null;
  warnings?: string[];
  result?: ImportPositionImageResponse | null;
  boardMap?: EditableBoard;
  boardReferenceUrl?: string | null;
}): ImageImportDraft {
  return {
    previewUrl: params.previewUrl,
    boardReferenceUrl: params.boardReferenceUrl ?? null,
    result: params.result ?? null,
    boardMap: params.boardMap ?? editableBoardFromFen(params.fen),
    sideToMove: params.sideToMove ?? sideToMoveFromFen(params.fen),
    userSide: params.userSide,
    humanProfile: params.humanProfile,
    boardOrientation: params.boardOrientation,
    status: params.status,
    message: params.message ?? null,
    confidence: params.confidence ?? null,
    warnings: params.warnings ?? []
  };
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error("Lecture de l'image impossible."));
    reader.readAsDataURL(file);
  });
}

async function prepareImageForImport(file: File) {
  const browserReadableType = file.type ? file.type.toLowerCase() : "image/jpeg";
  if (!browserReadableType.startsWith("image/")) {
    throw new Error("Fichier non supporte. Envoie une photo ou une capture d'ecran.");
  }
  if (file.size > IMAGE_IMPORT_MAX_SOURCE_BYTES) {
    throw new Error("Image trop lourde pour le telephone. Fais une capture d'ecran plus simple du plateau.");
  }

  const sourceDataUrl = await readFileAsDataUrl(file);
  const compressedDataUrl = await compressImageDataUrl(sourceDataUrl);
  const cropDataUrls = await createImageImportCropDataUrls(sourceDataUrl);
  return {
    previewUrl: compressedDataUrl,
    imageData: dataUrlToBase64(compressedDataUrl),
    mimeType: mimeTypeFromDataUrl(compressedDataUrl) || "image/jpeg",
    imageVariants: cropDataUrls.map<PreparedImageVariant>((variant) => ({
      imageData: dataUrlToBase64(variant.dataUrl),
      mimeType: mimeTypeFromDataUrl(variant.dataUrl) || "image/jpeg",
      label: variant.label,
      dataUrl: variant.dataUrl
    })).slice(0, 4),
    localCandidateDataUrls: [compressedDataUrl, ...cropDataUrls.map((variant) => variant.dataUrl)],
    fileName: file.name || "position.jpg"
  };
}

async function compressImageDataUrl(dataUrl: string) {
  const image = await loadImage(dataUrl);
  let fallbackDataUrl = dataUrl;

  for (const maxDimension of IMAGE_IMPORT_DIMENSIONS) {
    const scale = Math.min(1, maxDimension / Math.max(image.naturalWidth || image.width, image.naturalHeight || image.height));
    const width = Math.max(1, Math.round((image.naturalWidth || image.width) * scale));
    const height = Math.max(1, Math.round((image.naturalHeight || image.height) * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("Compression image indisponible sur ce navigateur.");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.drawImage(image, 0, 0, width, height);

    for (const quality of IMAGE_IMPORT_QUALITIES) {
      const blob = await canvasToBlob(canvas, "image/jpeg", quality);
      if (!blob) continue;
      const nextDataUrl = await blobToDataUrl(blob);
      fallbackDataUrl = nextDataUrl;
      if (blob.size <= IMAGE_IMPORT_TARGET_BYTES) {
        return nextDataUrl;
      }
    }
  }

  return fallbackDataUrl;
}

async function createImageImportCropDataUrls(dataUrl: string) {
  const image = await loadImage(dataUrl);
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  const crops = imageImportCropRects(width, height);
  const variants: Array<{ label: string; dataUrl: string }> = [];

  for (const crop of crops) {
    const cropped = await compressImageCrop(image, crop);
    if (cropped) variants.push({ label: crop.label, dataUrl: cropped });
  }

  return variants.slice(0, 14);
}

function imageImportCropRects(width: number, height: number) {
  const maxSquare = Math.min(width, height);
  const crops: Array<{ x: number; y: number; width: number; height: number; label: string }> = [];
  const seen = new Set<string>();

  function addCrop(centerXRatio: number, centerYRatio: number, sizeRatio: number, label: string) {
    const cropSize = Math.max(64, Math.round(maxSquare * sizeRatio));
    const centerX = width * centerXRatio;
    const centerY = height * centerYRatio;
    const x = Math.max(0, Math.min(width - cropSize, Math.round(centerX - cropSize / 2)));
    const y = Math.max(0, Math.min(height - cropSize, Math.round(centerY - cropSize / 2)));
    const key = `${x}:${y}:${cropSize}`;
    if (seen.has(key)) return;
    seen.add(key);
    crops.push({ x, y, width: cropSize, height: cropSize, label });
  }

  addCrop(0.5, 0.5, 1, "crop carre centre");
  addCrop(0.5, 0.5, 0.9, "crop centre serre");
  addCrop(0.5, 0.5, 0.78, "crop centre proche");

  if (width >= height) {
    addCrop(0.33, 0.5, 1, "crop gauche");
    addCrop(0.67, 0.5, 1, "crop droit");
    addCrop(0.25, 0.5, 0.9, "crop gauche serre");
    addCrop(0.75, 0.5, 0.9, "crop droit serre");
  }

  if (height >= width) {
    addCrop(0.5, 0.34, 1, "crop haut");
    addCrop(0.5, 0.66, 1, "crop bas");
    addCrop(0.5, 0.25, 0.9, "crop haut serre");
    addCrop(0.5, 0.75, 0.9, "crop bas serre");
  }

  addCrop(0.28, 0.34, 0.82, "crop haut gauche");
  addCrop(0.72, 0.34, 0.82, "crop haut droit");
  addCrop(0.28, 0.66, 0.82, "crop bas gauche");
  addCrop(0.72, 0.66, 0.82, "crop bas droit");

  return crops;
}

async function compressImageCrop(image: HTMLImageElement, crop: { x: number; y: number; width: number; height: number }) {
  let fallbackDataUrl: string | null = null;
  for (const maxDimension of [1000, 820, 680]) {
    const scale = Math.min(1, maxDimension / Math.max(crop.width, crop.height));
    const width = Math.max(1, Math.round(crop.width * scale));
    const height = Math.max(1, Math.round(crop.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("Compression image indisponible sur ce navigateur.");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.drawImage(image, crop.x, crop.y, crop.width, crop.height, 0, 0, width, height);

    for (const quality of [0.78, 0.62, 0.5]) {
      const blob = await canvasToBlob(canvas, "image/jpeg", quality);
      if (!blob) continue;
      const nextDataUrl = await blobToDataUrl(blob);
      fallbackDataUrl = nextDataUrl;
      if (blob.size <= IMAGE_IMPORT_TARGET_BYTES) {
        return nextDataUrl;
      }
    }
  }
  return fallbackDataUrl;
}

function loadImage(dataUrl: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.decoding = "async";
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Cette photo n'est pas lisible. Essaie une capture d'ecran PNG ou JPEG du plateau."));
    image.src = dataUrl;
  });
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number) {
  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob((blob) => resolve(blob), type, quality);
  });
}

function blobToDataUrl(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error("Compression image impossible."));
    reader.readAsDataURL(blob);
  });
}

function mimeTypeFromDataUrl(dataUrl: string) {
  const match = /^data:([^;,]+)[;,]/.exec(dataUrl);
  return match?.[1] ?? null;
}

async function detectPositionLocally(dataUrls: string[]): Promise<LocalBoardDetection | null> {
  const detections: LocalBoardDetection[] = [];
  for (const dataUrl of dataUrls.slice(0, 15)) {
    try {
      const detection = await detectPositionFromSquareImage(dataUrl);
      if (isUsableLocalDetection(detection)) detections.push(detection);
      detections.push({
        boardMap: rotateEditableBoard(detection.boardMap),
        confidence: Math.max(0, detection.confidence - 4),
        warnings: [...detection.warnings, "Orientation retournee testee automatiquement."],
        referenceUrl: detection.referenceUrl
      });
    } catch {
      continue;
    }
  }
  const usable = detections.filter(isUsableLocalDetection);
  if (!usable.length) return null;
  return usable.sort((a, b) => localDetectionScore(b) - localDetectionScore(a))[0];
}

function localDetectionScore(detection: LocalBoardDetection) {
  const pieces = Object.values(detection.boardMap).filter(Boolean);
  const hasWhiteKing = pieces.includes("K");
  const hasBlackKing = pieces.includes("k");
  let score = detection.confidence;
  score += Math.min(32, pieces.length) * 1.8;
  if (pieces.length >= 4 && pieces.length <= 32) score += 18;
  if (hasWhiteKing) score += 14;
  if (hasBlackKing) score += 14;
  if (hasWhiteKing && hasBlackKing) score += 24;
  if (editableBoardIsValid(detection.boardMap, "white")) score += 24;
  if (pieces.length > 32) score -= 80;
  return score;
}

function isUsableLocalDetection(detection: LocalBoardDetection) {
  const pieces = Object.values(detection.boardMap).filter(Boolean) as EditablePiece[];
  const whitePieces = pieces.filter((piece) => piece === piece.toUpperCase());
  const blackPieces = pieces.filter((piece) => piece === piece.toLowerCase());
  const whitePawns = pieces.filter((piece) => piece === "P").length;
  const blackPawns = pieces.filter((piece) => piece === "p").length;
  const whiteKings = pieces.filter((piece) => piece === "K").length;
  const blackKings = pieces.filter((piece) => piece === "k").length;
  const queens = pieces.filter((piece) => piece.toLowerCase() === "q").length;
  const rooks = pieces.filter((piece) => piece.toLowerCase() === "r").length;
  const bishops = pieces.filter((piece) => piece.toLowerCase() === "b").length;
  const knights = pieces.filter((piece) => piece.toLowerCase() === "n").length;

  if (pieces.length < 2 || pieces.length > 32) return false;
  if (whitePieces.length > 16 || blackPieces.length > 16) return false;
  if (whitePawns > 8 || blackPawns > 8) return false;
  if (whiteKings !== 1 || blackKings !== 1) return false;
  if (queens > 8 || rooks > 10 || bishops > 10 || knights > 10) return false;
  if (detection.confidence < 38) return false;
  return true;
}

async function detectPositionFromSquareImage(dataUrl: string): Promise<LocalBoardDetection> {
  const image = await loadImage(dataUrl);
  const sourceWidth = image.naturalWidth || image.width;
  const sourceHeight = image.naturalHeight || image.height;
  const sourceSquare = Math.min(sourceWidth, sourceHeight);
  const sourceX = Math.max(0, Math.round((sourceWidth - sourceSquare) / 2));
  const sourceY = Math.max(0, Math.round((sourceHeight - sourceSquare) / 2));
  const canvas = document.createElement("canvas");
  canvas.width = LOCAL_IMAGE_IMPORT_CANVAS_SIZE;
  canvas.height = LOCAL_IMAGE_IMPORT_CANVAS_SIZE;
  const context = canvas.getContext("2d", { alpha: false });
  if (!context) throw new Error("Detection locale image indisponible.");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, sourceX, sourceY, sourceSquare, sourceSquare, 0, 0, canvas.width, canvas.height);
  const referenceUrl = canvas.toDataURL("image/jpeg", 0.86);
  const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
  const board = emptyEditableBoard();
  const detections: LocalSquareDetection[] = [];
  const squareSize = canvas.width / 8;

  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 8; col += 1) {
      const square = `${EDITABLE_FILES[col]}${8 - row}`;
      const detection = detectLocalSquare(imageData, square, col * squareSize, row * squareSize, squareSize);
      detections.push(detection);
      board[square] = detection.piece;
    }
  }

  repairLocalBackRankPieces(board);
  const occupied = detections.filter((item) => item.occupied);
  const confidence = Math.max(0, Math.min(86, Math.round(
    occupied.length
      ? occupied.reduce((total, item) => total + item.confidence, 0) / occupied.length
      : 18
  )));
  const warnings = [
    "Detection locale automatique sans quota: verifie les pieces avant de valider."
  ];
  if (!editableBoardIsValid(board, "white")) {
    warnings.push("La detection locale peut etre incomplete; corrige les rois et les pieces manquantes.");
  }
  return { boardMap: board, confidence, warnings, referenceUrl };
}

function detectLocalSquare(imageData: ImageData, square: string, x: number, y: number, size: number): LocalSquareDetection {
  const margin = Math.max(4, Math.round(size * 0.11));
  const background = sampleSquareBackground(imageData, x, y, size);
  let count = 0;
  let lightCount = 0;
  let darkCount = 0;
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = 0;
  let maxY = 0;
  let leftCount = 0;
  let rightCount = 0;
  let topCount = 0;
  let middleCount = 0;
  let bottomCount = 0;
  const maskCounts = new Array<number>(LOCAL_TEMPLATE_SIZE * LOCAL_TEMPLATE_SIZE).fill(0);

  for (let py = Math.round(y + margin); py < Math.round(y + size - margin); py += 2) {
    for (let px = Math.round(x + margin); px < Math.round(x + size - margin); px += 2) {
      const index = (py * imageData.width + px) * 4;
      const r = imageData.data[index];
      const g = imageData.data[index + 1];
      const b = imageData.data[index + 2];
      const distance = colorDistance({ r, g, b }, background);
      const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      const isForeground = distance > 42 || luminance < background.luminance - 48 || luminance > background.luminance + 54;
      if (!isForeground) continue;
      count += 1;
      if (luminance > 150) lightCount += 1;
      if (luminance < 112) darkCount += 1;
      minX = Math.min(minX, px);
      minY = Math.min(minY, py);
      maxX = Math.max(maxX, px);
      maxY = Math.max(maxY, py);
      if (px < x + size / 2) leftCount += 1;
      else rightCount += 1;
      const relativeY = (py - y) / size;
      if (relativeY < 0.34) topCount += 1;
      else if (relativeY < 0.68) middleCount += 1;
      else bottomCount += 1;
      const maskX = Math.max(0, Math.min(LOCAL_TEMPLATE_SIZE - 1, Math.floor(((px - x) / size) * LOCAL_TEMPLATE_SIZE)));
      const maskY = Math.max(0, Math.min(LOCAL_TEMPLATE_SIZE - 1, Math.floor(((py - y) / size) * LOCAL_TEMPLATE_SIZE)));
      maskCounts[maskY * LOCAL_TEMPLATE_SIZE + maskX] += 1;
    }
  }

  const sampledArea = Math.max(1, ((size - margin * 2) / 2) ** 2);
  const fillRatio = count / sampledArea;
  if (fillRatio < 0.045 || count < 24) {
    return { square, piece: null, confidence: 0, occupied: false };
  }

  const pieceColor = lightCount >= darkCount * 0.72 ? "white" : "black";
  const pieceType = classifyLocalPiece({
    square,
    fillRatio,
    widthRatio: Math.max(0, (maxX - minX) / size),
    heightRatio: Math.max(0, (maxY - minY) / size),
    asymmetry: Math.abs(leftCount - rightCount) / Math.max(1, count),
    topRatio: topCount / Math.max(1, count),
    middleRatio: middleCount / Math.max(1, count),
    bottomRatio: bottomCount / Math.max(1, count),
    mask: maskCounts.map((value) => value > 0)
  });
  const piece = pieceColor === "white" ? pieceType.toUpperCase() : pieceType;
  const confidence = Math.round(Math.max(38, Math.min(84, 44 + fillRatio * 100 + Math.min(18, count / 38))));
  return { square, piece: piece as EditablePiece, confidence, occupied: true };
}

function sampleSquareBackground(imageData: ImageData, x: number, y: number, size: number) {
  const patches = [
    [x + size * 0.13, y + size * 0.13],
    [x + size * 0.87, y + size * 0.13],
    [x + size * 0.13, y + size * 0.87],
    [x + size * 0.87, y + size * 0.87]
  ];
  let r = 0;
  let g = 0;
  let b = 0;
  let total = 0;
  for (const [cx, cy] of patches) {
    for (let dy = -3; dy <= 3; dy += 3) {
      for (let dx = -3; dx <= 3; dx += 3) {
        const px = Math.max(0, Math.min(imageData.width - 1, Math.round(cx + dx)));
        const py = Math.max(0, Math.min(imageData.height - 1, Math.round(cy + dy)));
        const index = (py * imageData.width + px) * 4;
        r += imageData.data[index];
        g += imageData.data[index + 1];
        b += imageData.data[index + 2];
        total += 1;
      }
    }
  }
  const color = {
    r: r / total,
    g: g / total,
    b: b / total
  };
  return {
    ...color,
    luminance: 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b
  };
}

function colorDistance(color: { r: number; g: number; b: number }, background: { r: number; g: number; b: number }) {
  return Math.sqrt((color.r - background.r) ** 2 + (color.g - background.g) ** 2 + (color.b - background.b) ** 2);
}

function classifyLocalPiece(features: {
  square: string;
  fillRatio: number;
  widthRatio: number;
  heightRatio: number;
  asymmetry: number;
  topRatio: number;
  middleRatio: number;
  bottomRatio: number;
  mask: boolean[];
}): Lowercase<EditablePiece> {
  const file = features.square[0];
  const rank = Number(features.square[1]);

  if (rank === 2 || rank === 7) return "p";
  if (rank === 1 || rank === 8) {
    if (file === "a" || file === "h") return "r";
    if (file === "b" || file === "g") return "n";
    if (file === "c" || file === "f") return "b";
    if (file === "d") return "q";
      if (file === "e") return "k";
  }

  const templateMatch = bestLocalTemplateMatch(features.mask);
  if (templateMatch && templateMatch.score >= 0.44) {
    return templateMatch.piece;
  }

  if (features.heightRatio < 0.54 && features.widthRatio < 0.58) return "p";
  if (features.asymmetry > 0.18 && features.widthRatio > 0.38 && features.middleRatio > 0.30) return "n";
  if (features.widthRatio > 0.62 && features.topRatio > 0.20 && features.bottomRatio > 0.25) return "r";
  if (features.heightRatio > 0.68 && features.widthRatio < 0.52) return "b";
  if (features.heightRatio > 0.66 && features.widthRatio > 0.58 && features.topRatio > 0.24) return "q";
  if (features.heightRatio > 0.64 && features.widthRatio > 0.50) return "k";
  return features.fillRatio > 0.18 ? "b" : "p";
}

const localTemplateCache = new Map<Lowercase<EditablePiece>, boolean[]>();

function bestLocalTemplateMatch(mask: boolean[]) {
  let best: { piece: Lowercase<EditablePiece>; score: number } | null = null;
  for (const piece of ["k", "q", "r", "b", "n", "p"] as Array<Lowercase<EditablePiece>>) {
    const template = localTemplateMask(piece);
    const score = compareLocalMasks(mask, template);
    if (!best || score > best.score) {
      best = { piece, score };
    }
  }
  return best;
}

function localTemplateMask(piece: Lowercase<EditablePiece>) {
  const cached = localTemplateCache.get(piece);
  if (cached) return cached;
  const canvas = document.createElement("canvas");
  canvas.width = 72;
  canvas.height = 72;
  const context = canvas.getContext("2d");
  if (!context) return new Array<boolean>(LOCAL_TEMPLATE_SIZE * LOCAL_TEMPLATE_SIZE).fill(false);
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#000000";
  context.font = "58px Georgia, 'Times New Roman', serif";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(LOCAL_TEMPLATE_SYMBOLS[piece], canvas.width / 2, canvas.height / 2 + 2);
  const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
  const mask = new Array<boolean>(LOCAL_TEMPLATE_SIZE * LOCAL_TEMPLATE_SIZE).fill(false);
  const binWidth = canvas.width / LOCAL_TEMPLATE_SIZE;
  const binHeight = canvas.height / LOCAL_TEMPLATE_SIZE;
  for (let y = 0; y < LOCAL_TEMPLATE_SIZE; y += 1) {
    for (let x = 0; x < LOCAL_TEMPLATE_SIZE; x += 1) {
      let active = 0;
      let samples = 0;
      for (let py = Math.floor(y * binHeight); py < Math.floor((y + 1) * binHeight); py += 1) {
        for (let px = Math.floor(x * binWidth); px < Math.floor((x + 1) * binWidth); px += 1) {
          active += data[(py * canvas.width + px) * 4 + 3] > 20 ? 1 : 0;
          samples += 1;
        }
      }
      mask[y * LOCAL_TEMPLATE_SIZE + x] = active / Math.max(1, samples) > 0.12;
    }
  }
  localTemplateCache.set(piece, mask);
  return mask;
}

function compareLocalMasks(a: boolean[], b: boolean[]) {
  let intersection = 0;
  let union = 0;
  let aCount = 0;
  let bCount = 0;
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    if (a[index]) aCount += 1;
    if (b[index]) bCount += 1;
    if (a[index] || b[index]) union += 1;
    if (a[index] && b[index]) intersection += 1;
  }
  if (!union) return 0;
  const coveragePenalty = Math.abs(aCount - bCount) / Math.max(aCount, bCount, 1);
  return intersection / union - coveragePenalty * 0.12;
}

function repairLocalBackRankPieces(board: EditableBoard) {
  const backRanks: Array<{ color: "white" | "black"; rank: string; pieces: EditablePiece[] }> = [
    { color: "white", rank: "1", pieces: ["R", "N", "B", "Q", "K", "B", "N", "R"] },
    { color: "black", rank: "8", pieces: ["r", "n", "b", "q", "k", "b", "n", "r"] }
  ];
  for (const backRank of backRanks) {
    const rankPieces = EDITABLE_FILES.map((file) => board[`${file}${backRank.rank}`]).filter(Boolean) as EditablePiece[];
    const sameColorCount = rankPieces.filter((piece) => backRank.color === "white" ? piece === piece.toUpperCase() : piece === piece.toLowerCase()).length;
    const opponentCount = rankPieces.length - sameColorCount;
    if (sameColorCount < 4 || opponentCount > 0) continue;
    for (let index = 0; index < EDITABLE_FILES.length; index += 1) {
      const square = `${EDITABLE_FILES[index]}${backRank.rank}`;
      const piece = board[square];
      if (!piece) continue;
      const isSameColor = backRank.color === "white" ? piece === piece.toUpperCase() : piece === piece.toLowerCase();
      if (isSameColor) board[square] = backRank.pieces[index];
    }
  }
}

function urlForSnapshot(snapshot: NavigationSnapshot) {
  const params = new URLSearchParams();
  if (snapshot.appStage === "white-plan-selection") {
    params.set("view", "white-plans");
  } else if (snapshot.appStage === "black-first-move") {
    params.set("view", "black-first-move");
  } else if (snapshot.appStage === "black-plan-selection") {
    params.set("view", "black-plans");
    if (snapshot.firstOpponentMove) params.set("first", snapshot.firstOpponentMove);
  } else if (snapshot.appStage === "coach") {
    params.set("view", "coach");
    params.set("side", snapshot.userSide);
    if (snapshot.selectedPlanId) params.set("plan", snapshot.selectedPlanId);
    if (snapshot.firstOpponentMove) params.set("first", snapshot.firstOpponentMove);
  }
  if (snapshot.historyUci.length > 0 || (snapshot.appStage === "coach" && Boolean(snapshot.firstOpponentMove))) {
    params.set("moves", snapshot.historyUci.join(","));
  }
  if (snapshot.appStage !== "side-selection") {
    params.set("profile", snapshot.humanProfile);
  }
  const query = params.toString();
  return `${window.location.pathname}${query ? `?${query}` : ""}`;
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

export default function HomePage() {
  const [game, setGame] = useState(() => new Chess());
  const [baseFen, setBaseFen] = useState<string | null>(null);
  const [appStage, setAppStage] = useState<AppStage>("side-selection");
  const [userSide, setUserSide] = useState<UserSide>("white");
  const [orientation, setOrientation] = useState<Orientation>("white");
  const [mode, setMode] = useState<PlayMode>("both");
  const [humanProfile, setHumanProfile] = useState<CoachHumanProfile>(DEFAULT_HUMAN_PROFILE);
  const [boardWidth, setBoardWidth] = useState(360);
  const [selectedSquare, setSelectedSquare] = useState<string | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<PendingPromotion | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [plans, setPlans] = useState<StrategyPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [plansError, setPlansError] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [firstOpponentMove, setFirstOpponentMove] = useState<string | null>(null);
  const [planRecommendations, setPlanRecommendations] = useState<PlanRecommendationsResponse | null>(null);
  const [planRecommendationsFen, setPlanRecommendationsFen] = useState<string | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [botThinking, setBotThinking] = useState(false);
  const [botError, setBotError] = useState<string | null>(null);
  const [highlightedMove, setHighlightedMove] = useState<{ from: string; to: string } | null>(null);
  const [botStrategyState, setBotStrategyState] = useState<Record<string, unknown>>({});
  const [moveSources, setMoveSources] = useState<MoveSource[]>([]);
  const [redoStack, setRedoStack] = useState<TimelineMove[]>([]);
  const [adaptiveBoost, setAdaptiveBoost] = useState(0);
  const [eloChange, setEloChange] = useState<EloChange | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [imageImporting, setImageImporting] = useState(false);
  const [imageImportError, setImageImportError] = useState<string | null>(null);
  const [imageImportDraft, setImageImportDraft] = useState<ImageImportDraft | null>(null);
  const [fenImportOpen, setFenImportOpen] = useState(false);
  const [fenImportValue, setFenImportValue] = useState("");
  const [fenImportError, setFenImportError] = useState<string | null>(null);
  const [fenImportUserSide, setFenImportUserSide] = useState<"white" | "black">("white");
  const [fenImportProfile, setFenImportProfile] = useState<CoachHumanProfile>(DEFAULT_HUMAN_PROFILE);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const navigationReady = useRef(false);
  const skipNextHistoryReplace = useRef(false);
  const lastEloAdjustmentPly = useRef<number | null>(null);
  const eloTrend = useRef(freshEloTrendState());
  const previousEffectiveElo = useRef<number | null>(null);
  const eloChangeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const botRequestInFlight = useRef(false);
  const botRequestSerial = useRef(0);
  const imageImportSerial = useRef(0);
  const botPausedByTimelineNavigation = useRef(false);
  const skipNextAdaptiveSignalForTimeline = useRef(false);
  const lastTimelineTouchAt = useRef(0);
  const timelineRef = useRef<{ historyUci: string[]; moveSources: MoveSource[]; redoStack: TimelineMove[] }>({
    historyUci: [],
    moveSources: [],
    redoStack: []
  });

  const fen = game.fen();
  const history = useMemo(() => game.history({ verbose: true }) as VerboseMove[], [game]);
  const status = useMemo(() => gameStatus(game), [game]);
  const pgn = useMemo(() => game.pgn(), [game]);
  const historyUci = useMemo(() => history.map((move) => `${move.from}${move.to}${move.promotion ?? ""}`), [history]);
  const checkmateResult = useMemo(() => {
    if (!game.isCheckmate()) return null;
    const winner = game.turn() === "w" ? "Les noirs" : "Les blancs";
    const matedKing = game.turn() === "w" ? "blanc" : "noir";
    return {
      winner,
      detail: `Le roi ${matedKing} n'a plus d'echappatoire.`
    };
  }, [game]);
  const baseCoachElo = useMemo(() => baseEloForProfile(humanProfile), [humanProfile]);
  const effectiveCoachElo = useMemo(() => effectiveElo(baseCoachElo, adaptiveBoost), [adaptiveBoost, baseCoachElo]);
  const activeSkillLevel = useMemo(() => skillLevelForElo(effectiveCoachElo), [effectiveCoachElo]);
  const eloPressureLabel = useMemo(() => {
    const pressure = planRecommendations?.adaptiveSignal?.pressure;
    if (pressure === "critical") return "Pression forte";
    if (pressure === "drawish") return "Eviter la nulle";
    if (pressure === "worse") return "Position tendue";
    return "Stable";
  }, [planRecommendations?.adaptiveSignal?.pressure]);
  const botTurnInBotMode = useMemo(() => {
    if (appStage !== "coach" || mode === "both" || game.isGameOver() || pendingPromotion) return false;
    return mode === "white" ? game.turn() === "b" : game.turn() === "w";
  }, [appStage, game, mode, pendingPromotion]);
  const lastBoardMove = useMemo(() => {
    const move = history[history.length - 1];
    return move ? { from: move.from, to: move.to } : null;
  }, [history]);
  const selectedPlan = useMemo(() => {
    return plans.find((plan) => plan.id === selectedPlanId) ?? (planRecommendations?.selectedPlan as StrategyPlan | null) ?? null;
  }, [plans, planRecommendations?.selectedPlan, selectedPlanId]);
  const boardLocked = appStage === "black-plan-selection" || appStage === "white-plan-selection" || appStage === "side-selection";
  const canStepBackward = canStepBack(historyUci.length);
  const canStepForward = !boardLocked && redoStack.length > 0;
  const firstMoveLabel = firstOpponentMove ? history[0]?.san ?? firstOpponentMove : null;
  const primaryRecommendation = planRecommendations?.primaryMove ?? null;
  const expectedOpponentRecommendation = planRecommendations?.expectedOpponentMove ?? null;
  const recommendationArrows = useMemo(
    () => {
      const arrows = primaryRecommendation
        ? [{
            from: primaryRecommendation.moveUci.slice(0, 2),
            to: primaryRecommendation.moveUci.slice(2, 4),
            color: primaryRecommendation.arrowColor ?? PLAYER_RECOMMENDATION_ARROW
          }]
        : [];
      if (planRecommendationsFen !== fen) return [];
      if (expectedOpponentRecommendation) {
        arrows.push({
          from: expectedOpponentRecommendation.moveUci.slice(0, 2),
          to: expectedOpponentRecommendation.moveUci.slice(2, 4),
          color: expectedOpponentRecommendation.arrowColor ?? OPPONENT_EXPECTED_ARROW
        });
      }
      return arrows;
    },
    [expectedOpponentRecommendation, fen, planRecommendationsFen, primaryRecommendation]
  );
  const makeNavigationSnapshot = useCallback(
    (overrides: Partial<NavigationSnapshot> = {}) =>
      createNavigationSnapshot({
        appStage,
        userSide,
        orientation,
        mode,
        humanProfile,
        selectedPlanId,
        firstOpponentMove,
        historyUci,
        importedFen: baseFen,
        ...overrides
      }),
    [appStage, baseFen, firstOpponentMove, historyUci, humanProfile, mode, orientation, selectedPlanId, userSide]
  );

  const writeNavigationSnapshot = useCallback((snapshot: NavigationSnapshot, action: "push" | "replace") => {
    if (typeof window === "undefined") return;
    const url = urlForSnapshot(snapshot);
    if (action === "push") {
      window.history.pushState(snapshot, "", url);
    } else {
      window.history.replaceState(snapshot, "", url);
    }
  }, []);

  const restoreNavigationSnapshot = useCallback((snapshot: NavigationSnapshot) => {
    const importedFen = snapshot.importedFen ?? null;
    const restoredGame = buildGameFromHistory(snapshot.historyUci, importedFen);
    const restoredHistoryUci = historyFromGame(restoredGame);
    const restoredMoveSources: MoveSource[] = restoredHistoryUci.map(() => "manual");
    timelineRef.current = { historyUci: restoredHistoryUci, moveSources: restoredMoveSources, redoStack: [] };
    setBaseFen(importedFen);
    setGame(restoredGame);
    setAppStage(snapshot.appStage);
    setUserSide(snapshot.userSide);
    setOrientation(snapshot.orientation);
    setMode(snapshot.mode);
    setHumanProfile(normalizeHumanProfile(snapshot.humanProfile));
    setSelectedPlanId(snapshot.selectedPlanId);
    setFirstOpponentMove(snapshot.firstOpponentMove);
    setMoveSources(restoredMoveSources);
    setRedoStack([]);
    setAdaptiveBoost(0);
    setEloChange(null);
    previousEffectiveElo.current = baseEloForProfile(normalizeHumanProfile(snapshot.humanProfile));
    lastEloAdjustmentPly.current = null;
    botRequestSerial.current += 1;
    botRequestInFlight.current = false;
    botPausedByTimelineNavigation.current = false;
    setSelectedSquare(null);
    setPendingPromotion(null);
    setLastMessage(null);
    imageImportSerial.current += 1;
    setImageImporting(false);
    setImageImportError(null);
    setImageImportDraft(null);
    setFenImportOpen(false);
    setFenImportValue("");
    setFenImportError(null);
    setFenImportProfile(normalizeHumanProfile(snapshot.humanProfile));
    if (snapshot.appStage === "side-selection" || snapshot.appStage === "black-first-move") {
      setPlans([]);
    }
    setPlansError(null);
    setPlanRecommendations(null);
    setPlanRecommendationsFen(null);
    setPlanError(null);
    setBotThinking(false);
    setBotError(null);
    setBotStrategyState({});
    setHighlightedMove(null);
    setImageImportError(null);
    setImageImportDraft(null);
    setImageImporting(false);
    setFenImportOpen(false);
    setFenImportError(null);
    setMenuOpen(false);
  }, []);

  const navigateToSnapshot = useCallback(
    (snapshot: NavigationSnapshot, action: "push" | "replace" = "push") => {
      restoreNavigationSnapshot(snapshot);
      writeNavigationSnapshot(snapshot, action);
    },
    [restoreNavigationSnapshot, writeNavigationSnapshot]
  );

  useEffect(() => {
    const historySnapshot = isNavigationSnapshot(window.history.state) ? window.history.state : null;
    const initialSnapshot = historySnapshot ?? snapshotFromLocation();
    restoreNavigationSnapshot(initialSnapshot);
    writeNavigationSnapshot(initialSnapshot, "replace");
    navigationReady.current = true;
    skipNextHistoryReplace.current = true;

    function handlePopState(event: PopStateEvent) {
      const snapshot = isNavigationSnapshot(event.state) ? event.state : snapshotFromLocation();
      restoreNavigationSnapshot(snapshot);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [restoreNavigationSnapshot, writeNavigationSnapshot]);

  useEffect(() => {
    if (!navigationReady.current) return;
    if (skipNextHistoryReplace.current) {
      skipNextHistoryReplace.current = false;
      return;
    }
    writeNavigationSnapshot(makeNavigationSnapshot(), "replace");
  }, [makeNavigationSnapshot, writeNavigationSnapshot]);

  useEffect(() => {
    const primaryUci = planRecommendations?.primaryMove?.moveUci ?? null;
    const hintUci = primaryUci ?? planRecommendations?.expectedOpponentMove?.moveUci ?? null;
    if (appStage !== "coach" || !hintUci || planRecommendationsFen !== fen) {
      setHighlightedMove(null);
      return;
    }
    setHighlightedMove({ from: hintUci.slice(0, 2), to: hintUci.slice(2, 4) });
  }, [appStage, fen, planRecommendations?.expectedOpponentMove?.moveUci, planRecommendations?.primaryMove?.moveUci, planRecommendationsFen]);

  useEffect(() => {
    function updateBoardWidth() {
      const viewportWidth = Math.min(
        window.innerWidth,
        window.outerWidth || window.innerWidth,
        document.documentElement.clientWidth || window.innerWidth,
        window.visualViewport?.width ?? window.innerWidth
      );
      const mobileViewport = viewportWidth <= 540;
      const horizontalReserve = mobileViewport ? 14 : 38;
      const maxBoardWidth = mobileViewport ? 520 : 720;
      const width = Math.min(viewportWidth - horizontalReserve, mobileViewport ? viewportWidth * 0.97 : viewportWidth * 0.9, maxBoardWidth);
      setBoardWidth(Math.floor(Math.max(240, width)));
    }
    updateBoardWidth();
    window.addEventListener("resize", updateBoardWidth);
    return () => window.removeEventListener("resize", updateBoardWidth);
  }, []);

  useEffect(() => {
    if (appStage !== "white-plan-selection" && appStage !== "black-plan-selection") return;

    const side = appStage === "white-plan-selection" ? "white" : "black";
    const firstMove = side === "black" ? firstOpponentMove ?? undefined : undefined;
    let active = true;
    setPlansLoading(true);
    setPlansError(null);

    listAvailablePlans(side, baseCoachElo, firstMove)
      .then((response) => {
        if (!active) return;
        setPlans(response.plans);
      })
      .catch((error: Error) => {
        if (!active) return;
        setPlans([]);
        setPlansError(error.message || "Impossible de charger les plans.");
      })
      .finally(() => {
        if (active) setPlansLoading(false);
      });

    return () => {
      active = false;
    };
  }, [appStage, baseCoachElo, firstOpponentMove]);

  useEffect(() => {
    if (appStage !== "coach") {
      setPlanRecommendations(null);
      setPlanRecommendationsFen(null);
      return;
    }
    if (botTurnInBotMode) {
      setPlanLoading(false);
      setPlanError(null);
      return;
    }

    let active = true;
    const controller = new AbortController();
    setPlanLoading(true);
    setPlanError(null);
    getPlanRecommendations({
      fen,
      selectedPlanId,
      userSide: userSide === "both" ? null : userSide,
      elo: effectiveCoachElo,
      skillLevel: activeSkillLevel,
      moveHistoryUci: historyUci,
      maxMoves: INTERNAL_MAX_MOVES,
      engineDepth: INTERNAL_ENGINE_DEPTH,
      signal: controller.signal
    })
      .then((response) => {
        if (active) {
          setPlanRecommendations(response);
          setPlanRecommendationsFen(fen);
        }
      })
      .catch((error: Error) => {
        if (isAbortError(error)) return;
        if (!active) return;
        setPlanRecommendations(null);
        setPlanRecommendationsFen(null);
        setPlanError(error.message || "Impossible de mettre a jour les coups.");
      })
      .finally(() => {
        if (active) setPlanLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [activeSkillLevel, appStage, botTurnInBotMode, effectiveCoachElo, fen, historyUci, selectedPlanId, userSide]);

  useEffect(() => {
    if (appStage !== "coach" || !planRecommendations?.adaptiveSignal) return;
    const currentPly = historyUci.length;
    if (skipNextAdaptiveSignalForTimeline.current) {
      skipNextAdaptiveSignalForTimeline.current = false;
      lastEloAdjustmentPly.current = currentPly;
      return;
    }
    if (lastEloAdjustmentPly.current === currentPly) return;
    lastEloAdjustmentPly.current = currentPly;
    const lastMoveIndex = currentPly - 1;
    const lastMoveColor = lastMoveIndex >= 0 ? (lastMoveIndex % 2 === 0 ? "white" : "black") : null;
    const lastMoveSource = lastMoveIndex >= 0 ? moveSources[lastMoveIndex] : null;
    const lastMoveWasPlayer = userSide !== "both" && lastMoveColor === userSide && lastMoveSource !== "bot";

    const result = applyAdaptiveSignal({
      currentBoost: adaptiveBoost,
      pressure: planRecommendations.adaptiveSignal.pressure,
      suggestedBoostDelta: planRecommendations.adaptiveSignal.suggestedBoostDelta ?? 0,
      trend: eloTrend.current,
      lastMoveWasPlayer
    });
    eloTrend.current = result.trend;
    if (result.boost !== adaptiveBoost) {
      setAdaptiveBoost(result.boost);
    }
  }, [adaptiveBoost, appStage, historyUci.length, moveSources, planRecommendations?.adaptiveSignal, userSide]);

  useEffect(() => {
    if (appStage !== "coach") {
      previousEffectiveElo.current = effectiveCoachElo;
      setEloChange(null);
      return;
    }

    const previous = previousEffectiveElo.current;
    previousEffectiveElo.current = effectiveCoachElo;
    if (previous === null || previous === effectiveCoachElo) return;

    if (eloChangeTimer.current) {
      clearTimeout(eloChangeTimer.current);
    }
    setEloChange({
      id: Date.now(),
      previous,
      current: effectiveCoachElo,
      delta: effectiveCoachElo - previous
    });
    eloChangeTimer.current = setTimeout(() => setEloChange(null), 3600);
  }, [appStage, effectiveCoachElo]);

  useEffect(() => {
    return () => {
      if (eloChangeTimer.current) {
        clearTimeout(eloChangeTimer.current);
      }
    };
  }, []);

  const legalTargets = useMemo(() => {
    if (!selectedSquare || boardLocked) return [];
    return game.moves({ square: selectedSquare as Square, verbose: true }).map((move) => move.to);
  }, [boardLocked, game, selectedSquare]);

  const getCurrentTimeline = useCallback(() => timelineRef.current, []);

  const applyMove = useCallback(
    (from: string, to: string, promotion?: string, source: MoveSource = "manual") => {
      if (boardLocked) {
        setLastMessage("Choisis d'abord ton plan avant de continuer la partie.");
        return false;
      }
      if (source === "manual" && !canMoveInMode(game, mode)) {
        setLastMessage("Ce mode ne permet pas de jouer ce camp.");
        return false;
      }

      const result = tryMove(game, from, to, promotion);
      if (!result) {
        setLastMessage("Coup illegal refuse.");
        return false;
      }

      const moveUci = `${from}${to}${promotion ?? ""}`;
      const currentTimeline = getCurrentTimeline();
      const nextHistoryUci = [...currentTimeline.historyUci, moveUci];
      const nextMoveSources = [...currentTimeline.moveSources.slice(0, currentTimeline.historyUci.length), source];
      const nextGame = buildGameFromHistory(nextHistoryUci, baseFen);
      timelineRef.current = { historyUci: nextHistoryUci, moveSources: nextMoveSources, redoStack: [] };
      setGame(nextGame);
      setMoveSources(nextMoveSources);
      setRedoStack([]);
      if (source === "manual") {
        botPausedByTimelineNavigation.current = false;
        skipNextAdaptiveSignalForTimeline.current = false;
      }
      setSelectedSquare(null);
      setPendingPromotion(null);
      setBotError(null);
      setHighlightedMove(null);

      if (appStage === "black-first-move" && history.length === 0 && source === "manual") {
        const nextSnapshot = makeNavigationSnapshot({
          appStage: "black-plan-selection",
          userSide: "black",
          orientation: "black",
          selectedPlanId: null,
          firstOpponentMove: moveUci,
          historyUci: nextHistoryUci
        });
        setFirstOpponentMove(moveUci);
        setAppStage("black-plan-selection");
        setLastMessage("Premier coup blanc enregistre. Choisis maintenant une reponse noire.");
        writeNavigationSnapshot(nextSnapshot, "push");
      } else {
        setLastMessage(null);
      }
      return true;
    },
    [appStage, baseFen, boardLocked, game, getCurrentTimeline, history.length, makeNavigationSnapshot, mode, writeNavigationSnapshot]
  );

  const requestMove = useCallback(
    (from: string, to: string) => {
      if (isPromotionAttempt(game, from, to)) {
        setPendingPromotion({ from, to });
        return false;
      }
      return applyMove(from, to);
    },
    [applyMove, game]
  );

  useEffect(() => {
    if (appStage !== "coach" || (mode !== "white" && mode !== "black")) return;
    if (game.isGameOver() || pendingPromotion || botRequestInFlight.current || botError) return;

    const userTurn = mode === "white" ? game.turn() === "w" : game.turn() === "b";
    if (userTurn || botPausedByTimelineNavigation.current) return;

    let cancelled = false;
    const controller = new AbortController();
    const fenBefore = game.fen();
    const requestId = ++botRequestSerial.current;
    botRequestInFlight.current = true;
    setBotThinking(true);
    setBotError(null);

    requestBotMove({
      fen: fenBefore,
      elo: 3200,
      skillLevel: "pro",
      maxMoves: 1,
      engineDepth: BOT_ENGINE_DEPTH,
      botStyle: "balanced",
      selectedBotPlanId: selectedPlanId,
      userPlanId: selectedPlanId,
      strategyState: { ...botStrategyState, moveHistoryUci: historyUci },
      signal: controller.signal
    })
      .then((response) => {
        if (cancelled || requestId !== botRequestSerial.current) return;
        const from = response.move.moveUci.slice(0, 2);
        const to = response.move.moveUci.slice(2, 4);
        const promotion = response.move.moveUci.slice(4) || undefined;
        const botGame = new Chess(fenBefore);
        const result = tryMove(botGame, from, to, promotion);
        if (!result) {
          setBotError("Le bot a propose un coup illegal, il a ete refuse.");
          return;
        }
        setBotStrategyState(response.updatedStrategyState);
        const currentTimeline = timelineRef.current;
        const nextHistoryUci = [...currentTimeline.historyUci, response.move.moveUci];
        const nextMoveSources = [...currentTimeline.moveSources.slice(0, currentTimeline.historyUci.length), "bot" as MoveSource];
        const nextGame = buildGameFromHistory(nextHistoryUci, baseFen);
        timelineRef.current = { historyUci: nextHistoryUci, moveSources: nextMoveSources, redoStack: [] };
        setGame(nextGame);
        setMoveSources(nextMoveSources);
        setRedoStack([]);
        setHighlightedMove(null);
      })
      .catch((error: Error) => {
        if (cancelled || requestId !== botRequestSerial.current || isAbortError(error)) return;
        setBotError(error.message || "Le bot n'a pas pu jouer.");
      })
      .finally(() => {
        if (!cancelled && requestId === botRequestSerial.current) {
          botRequestInFlight.current = false;
          setBotThinking(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
      if (requestId === botRequestSerial.current) {
        botRequestInFlight.current = false;
        setBotThinking(false);
      }
    };
  }, [appStage, baseFen, botError, botStrategyState, game, historyUci, mode, pendingPromotion, selectedPlanId]);

  const handleSquareClick = useCallback(
    (square: string) => {
      if (boardLocked) return;
      const piece = game.get(square as Square);
      if (!selectedSquare) {
        if (piece && piece.color === game.turn() && canMoveInMode(game, mode)) {
          setSelectedSquare(square);
        }
        return;
      }

      if (selectedSquare === square) {
        setSelectedSquare(null);
        return;
      }

      if (piece && piece.color === game.turn()) {
        setSelectedSquare(square);
        return;
      }

      requestMove(selectedSquare, square);
    },
    [boardLocked, game, mode, requestMove, selectedSquare]
  );

  function startWhiteFlow(profile: CoachHumanProfile) {
    setHumanProfile(profile);
    setAdaptiveBoost(0);
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "white-plan-selection",
        userSide: "white",
        orientation: "white",
        humanProfile: profile,
        selectedPlanId: null,
        firstOpponentMove: null,
        historyUci: [],
        importedFen: null
      })
    );
  }

  function startBlackFlow(profile: CoachHumanProfile) {
    setHumanProfile(profile);
    setAdaptiveBoost(0);
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "black-first-move",
        userSide: "black",
        orientation: "black",
        humanProfile: profile,
        selectedPlanId: null,
        firstOpponentMove: null,
        historyUci: [],
        importedFen: null
      })
    );
  }

  function startFreeMode() {
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "coach",
        userSide: "both",
        orientation: "white",
        selectedPlanId: null,
        firstOpponentMove: null,
        historyUci: [],
        importedFen: null
      })
    );
  }

  const handlePlanSelect = useCallback(
    (planId: string) => {
      const plan = plans.find((item) => item.id === planId);
      const planOrientation: Orientation = plan?.side === "black" ? "black" : "white";
      navigateToSnapshot(
        makeNavigationSnapshot({
          appStage: "coach",
          userSide,
          orientation: planOrientation,
          selectedPlanId: planId,
          historyUci: userSide === "black" ? historyUci : [],
          firstOpponentMove: userSide === "black" ? firstOpponentMove : null
        })
      );
    },
    [firstOpponentMove, historyUci, makeNavigationSnapshot, navigateToSnapshot, plans, userSide]
  );

  const resetAdaptiveBoost = useCallback((profile: CoachHumanProfile = humanProfile) => {
    setAdaptiveBoost(0);
    setEloChange(null);
    previousEffectiveElo.current = baseEloForProfile(profile);
    lastEloAdjustmentPly.current = null;
    eloTrend.current = freshEloTrendState();
  }, [humanProfile]);

  function clearPositionDerivedState({ resetAdaptive = false }: { resetAdaptive?: boolean } = {}) {
    botRequestSerial.current += 1;
    setSelectedSquare(null);
    setPendingPromotion(null);
    setHighlightedMove(null);
    setLastMessage(null);
    setPlanRecommendations(null);
    setPlanRecommendationsFen(null);
    setPlanError(null);
    botRequestInFlight.current = false;
    setBotThinking(false);
    setBotError(null);
    setBotStrategyState({});
    if (resetAdaptive) {
      skipNextAdaptiveSignalForTimeline.current = false;
      resetAdaptiveBoost();
    }
  }

  function resetBoardOnly() {
    timelineRef.current = { historyUci: [], moveSources: [], redoStack: [] };
    botPausedByTimelineNavigation.current = false;
    setBaseFen(null);
    setGame(new Chess());
    setMoveSources([]);
    setRedoStack([]);
    clearPositionDerivedState({ resetAdaptive: true });
  }

  function undo() {
    const currentTimeline = getCurrentTimeline();
    const timeline = undoTimeline(
      currentTimeline.historyUci,
      currentTimeline.moveSources,
      currentTimeline.redoStack
    );
    if (!timeline.undoneMove) return;

    timelineRef.current = { historyUci: timeline.historyUci, moveSources: timeline.moveSources, redoStack: timeline.redoStack };
    botPausedByTimelineNavigation.current = true;
    skipNextAdaptiveSignalForTimeline.current = true;
    setGame(buildGameFromHistory(timeline.historyUci, baseFen));
    setMoveSources(timeline.moveSources);
    setRedoStack(timeline.redoStack);
    clearPositionDerivedState();

    if (userSide === "black" && timeline.historyUci.length === 0 && appStage !== "coach") {
      setSelectedPlanId(null);
      setFirstOpponentMove(null);
      setPlans([]);
      setAppStage("black-first-move");
    }
  }

  function redo() {
    const currentTimeline = getCurrentTimeline();
    const timeline = redoTimeline(currentTimeline.redoStack);
    if (!timeline.nextMove || boardLocked) return;

    const { moveUci, source } = timeline.nextMove;
    const baseGame = buildGameFromHistory(currentTimeline.historyUci, baseFen);
    const result = tryMove(baseGame, moveUci.slice(0, 2), moveUci.slice(2, 4), moveUci.slice(4) || undefined);
    if (!result) {
      timelineRef.current = { ...currentTimeline, redoStack: [] };
      setRedoStack([]);
      setLastMessage("Le coup suivant ne correspond plus a cette position.");
      return;
    }

    const nextHistoryUci = [...currentTimeline.historyUci, moveUci];
    const nextMoveSources = [...currentTimeline.moveSources, source];
    const nextGame = buildGameFromHistory(nextHistoryUci, baseFen);
    timelineRef.current = { historyUci: nextHistoryUci, moveSources: nextMoveSources, redoStack: timeline.redoStack };
    botPausedByTimelineNavigation.current = true;
    skipNextAdaptiveSignalForTimeline.current = true;
    setGame(nextGame);
    setMoveSources(nextMoveSources);
    setRedoStack(timeline.redoStack);
    clearPositionDerivedState();
  }

  function runTimelineTouch(event: TouchEvent<HTMLButtonElement>, action: () => void) {
    lastTimelineTouchAt.current = Date.now();
    event.preventDefault();
    event.stopPropagation();
    action();
  }

  function runTimelineClick(action: () => void) {
    if (Date.now() - lastTimelineTouchAt.current < 500) return;
    action();
  }

  function reset() {
    resetBoardOnly();
    if (userSide === "black") {
      setSelectedPlanId(null);
      setFirstOpponentMove(null);
      setPlans([]);
      setAppStage("black-first-move");
    }
  }

  function changePlan() {
    navigateToSnapshot(makeNavigationSnapshot({ appStage: "side-selection", userSide: "white", orientation: "white", selectedPlanId: null, firstOpponentMove: null, historyUci: [], importedFen: null }));
  }

  function goHome() {
    setMenuOpen(false);
    changePlan();
  }

  async function copyText(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    setLastMessage(`${label} copie.`);
  }

  function openImageImport() {
    setImageImportError(null);
    imageInputRef.current?.click();
  }

  function openFenImport() {
    setFenImportUserSide(userSide === "black" ? "black" : "white");
    setFenImportProfile(humanProfile);
    setFenImportValue("");
    setFenImportError(null);
    setFenImportOpen(true);
  }

  async function pasteFenFromClipboard() {
    try {
      const text = await navigator.clipboard.readText();
      setFenImportValue(text);
      setFenImportError(null);
    } catch {
      setFenImportError("Impossible de lire le presse-papiers. Colle le FEN manuellement.");
    }
  }

  function applyImportedFen(importedFen: string, side: "white" | "black", message: string, profile: CoachHumanProfile = humanProfile) {
    let importedGame: Chess;
    try {
      importedGame = new Chess(importedFen);
    } catch {
      throw new Error("FEN invalide. Verifie le texte copie.");
    }

    const keepSelectedPlan = selectedPlan?.side === side || selectedPlan?.side === "universal";
    timelineRef.current = { historyUci: [], moveSources: [], redoStack: [] };
    botPausedByTimelineNavigation.current = false;
    imageImportSerial.current += 1;
    setBaseFen(importedFen);
    setGame(importedGame);
    setHumanProfile(profile);
    setMoveSources([]);
    setRedoStack([]);
    setSelectedSquare(null);
    setPendingPromotion(null);
    setHighlightedMove(null);
    setLastMessage(message);
    setPlanRecommendations(null);
    setPlanRecommendationsFen(null);
    setPlanError(null);
    setBotError(null);
    botRequestInFlight.current = false;
    setBotThinking(false);
    setBotStrategyState({});
    resetAdaptiveBoost(profile);
    setAppStage("coach");
    setUserSide(side);
    setOrientation(side);
    setSelectedPlanId(keepSelectedPlan ? selectedPlanId : null);
    setFirstOpponentMove(null);
    writeNavigationSnapshot(
      makeNavigationSnapshot({
        appStage: "coach",
        userSide: side,
        orientation: side,
        humanProfile: profile,
        selectedPlanId: keepSelectedPlan ? selectedPlanId : null,
        firstOpponentMove: null,
        historyUci: [],
        importedFen
      }),
      "push"
    );
  }

  function confirmFenImport() {
    try {
      const importedFen = normalizeFenInput(fenImportValue);
      applyImportedFen(importedFen, fenImportUserSide, "Position importee depuis le FEN.", fenImportProfile);
      setFenImportOpen(false);
      setFenImportError(null);
      setMenuOpen(false);
    } catch (error) {
      setFenImportError(error instanceof Error ? error.message : "FEN invalide.");
    }
  }

  function updateImageImportDraft(updater: (draft: ImageImportDraft) => ImageImportDraft) {
    setImageImportDraft((current) => (current ? updater(current) : current));
  }

  function setImageImportSquare(square: string, piece: EditablePiece | null) {
    updateImageImportDraft((draft) => ({
      ...draft,
      boardMap: {
        ...draft.boardMap,
        [square]: piece
      },
      status: draft.status === "loading" ? "manual" : draft.status
    }));
  }

  function setImageImportBoard(boardMap: EditableBoard) {
    updateImageImportDraft((draft) => ({
      ...draft,
      boardMap,
      status: draft.status === "loading" ? "manual" : draft.status
    }));
  }

  async function handleImageFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (file.type && !file.type.toLowerCase().startsWith("image/")) {
      setImageImportError("Fichier non supporte. Utilise une photo ou une capture d'ecran.");
      return;
    }

    const importId = ++imageImportSerial.current;
    setImageImporting(true);
    setImageImportError(null);
    let draftOpened = false;
    try {
      const prepared = await prepareImageForImport(file);
      if (importId !== imageImportSerial.current) return;
      const localDetection = await detectPositionLocally(prepared.localCandidateDataUrls);
      if (importId !== imageImportSerial.current) return;
      const manualDraft = createImageImportDraft({
        previewUrl: prepared.previewUrl,
        boardReferenceUrl: localDetection?.referenceUrl ?? prepared.localCandidateDataUrls[1] ?? prepared.previewUrl,
        fen,
        boardMap: localDetection?.boardMap ?? emptyEditableBoard(),
        sideToMove: game.turn() === "b" ? "black" : "white",
        userSide: userSide === "black" ? "black" : "white",
        humanProfile,
        boardOrientation: boardOrientationFromOrientation(orientation),
        status: localDetection ? "local" : "loading",
        message: localDetection
          ? "Detection automatique locale active. Gemini peut encore ameliorer la lecture si disponible."
          : "Detection locale rejetee car trop incertaine. L'image reste en calque pour corriger vite.",
        confidence: localDetection?.confidence ?? null,
        warnings: localDetection?.warnings ?? ["Aucune position locale fiable n'a ete appliquee automatiquement."]
      });
      setImageImportDraft(manualDraft);
      draftOpened = true;

      const result = await importPositionImage({
        imageData: prepared.imageData,
        mimeType: prepared.mimeType,
        imageVariants: prepared.imageVariants,
        fileName: prepared.fileName
      });
      if (importId !== imageImportSerial.current) return;
      setImageImportDraft((current) =>
        createImageImportDraft({
          previewUrl: prepared.previewUrl,
          boardReferenceUrl: prepared.localCandidateDataUrls[1] ?? prepared.previewUrl,
          fen: result.fen,
          sideToMove: result.sideToMove,
          userSide: userSide === "black" ? "black" : "white",
          humanProfile: current?.humanProfile ?? humanProfile,
          boardOrientation: result.boardOrientation,
          status: "ready",
          message: result.confidence < 90 ? "Reconnaissance incertaine: verifie les pieces avant de valider." : "Position pre-remplie. Verifie puis valide.",
          confidence: result.confidence,
          warnings: result.warnings,
          result
        })
      );
    } catch (error) {
      if (importId !== imageImportSerial.current) return;
      const message = error instanceof Error ? error.message : "Reconnaissance automatique indisponible.";
      setImageImportDraft((current) =>
        current
          ? {
              ...current,
              result: null,
              status: current.status === "local" ? "local" : "manual",
              message: current.status === "local"
                ? "Detection locale conservee. Tu peux corriger puis valider."
                : "Reconnaissance automatique indisponible, correction manuelle ouverte.",
              warnings: []
            }
          : current
      );
      if (!draftOpened) {
        setImageImportError(message);
      }
    } finally {
      if (importId === imageImportSerial.current) setImageImporting(false);
    }
  }

  function confirmImageImport() {
    if (!imageImportDraft) return;
    const side = imageImportDraft.userSide;
    const importedFen = editableBoardToFen(imageImportDraft.boardMap, imageImportDraft.sideToMove);
    try {
      applyImportedFen(importedFen, side, "Position importee depuis l'image.", imageImportDraft.humanProfile);
    } catch (error) {
      setImageImportError(error instanceof Error ? error.message : "La position detectee n'est pas valide.");
      return;
    }
    setImageImportDraft(null);
    setImageImportError(null);
  }

  function cancelImageImportDraft() {
    imageImportSerial.current += 1;
    setImageImportDraft(null);
    setImageImporting(false);
    setImageImportError(null);
  }

  function handleHistoryClick(_ply: number, move: Move) {
    setHighlightedMove({ from: move.from, to: move.to });
  }

  const renderShell = (content: ReactNode) => (
    <>
      <input ref={imageInputRef} type="file" accept="image/*" className="sr-only" onChange={handleImageFileChange} />
      <SiteHeader
        status={appStage === "side-selection" ? null : status}
        menuOpen={menuOpen}
        imageImporting={imageImporting}
        onHome={goHome}
        onImportFen={openFenImport}
        onImportImage={openImageImport}
        onToggleMenu={() => setMenuOpen((open) => !open)}
      />
      {menuOpen ? (
        <SiteMenu status={status} onHome={goHome} onClose={() => setMenuOpen(false)}>
          {appStage === "side-selection" ? null : (
            <CoachUtilityMenu
              orientation={orientation}
              setOrientation={setOrientation}
              mode={mode}
              setMode={setMode}
              undo={undo}
              reset={reset}
              copyFen={() => copyText(fen, "FEN")}
              copyPgn={() => copyText(pgn || "*", "PGN")}
              history={history}
              handleHistoryClick={handleHistoryClick}
              fen={fen}
              pgn={pgn}
              historyUci={historyUci}
            />
          )}
        </SiteMenu>
      ) : null}
      {imageImportError ? (
        <div className="image-import-toast" role="alert">
          {imageImportError}
        </div>
      ) : null}
      {imageImportDraft ? (
        <ImageImportConfirmDialog
          draft={imageImportDraft}
          onSideToMoveChange={(sideToMove) => setImageImportDraft((current) => current ? { ...current, sideToMove } : current)}
          onUserSideChange={(side) => setImageImportDraft((current) => current ? { ...current, userSide: side } : current)}
          onProfileChange={(profile) => setImageImportDraft((current) => current ? { ...current, humanProfile: profile } : current)}
          onOrientationChange={(nextOrientation) =>
            setImageImportDraft((current) => {
              if (!current) return current;
              const nextBoardOrientation = boardOrientationFromOrientation(nextOrientation);
              if (current.boardOrientation === nextBoardOrientation) return current;
              return {
                ...current,
                boardOrientation: nextBoardOrientation,
                boardMap: rotateEditableBoard(current.boardMap)
              };
            })
          }
          onSquareChange={setImageImportSquare}
          onClearBoard={() => setImageImportBoard(emptyEditableBoard())}
          onUseCurrentBoard={() => setImageImportBoard(editableBoardFromFen(fen))}
          onUseStartingBoard={() => setImageImportBoard(editableBoardFromFen(new Chess().fen()))}
          onCancel={cancelImageImportDraft}
          onConfirm={confirmImageImport}
        />
      ) : null}
      {fenImportOpen ? (
        <FenImportDialog
          value={fenImportValue}
          error={fenImportError}
          userSide={fenImportUserSide}
          profile={fenImportProfile}
          onValueChange={setFenImportValue}
          onUserSideChange={setFenImportUserSide}
          onProfileChange={setFenImportProfile}
          onPaste={pasteFenFromClipboard}
          onCancel={() => setFenImportOpen(false)}
          onConfirm={confirmFenImport}
        />
      ) : null}
      {content}
    </>
  );

  if (appStage === "side-selection") {
    return renderShell(
      <main>
        <SideSelectionPanel onChooseWhite={startWhiteFlow} onChooseBlack={startBlackFlow} onChooseFreeMode={startFreeMode} />
      </main>
    );
  }

  if (appStage === "black-first-move") {
    return renderShell(
      <main className="first-move-shell">
        <section className="first-move-board">
          <ChessCoachBoard
            fen={fen}
            boardWidth={boardWidth}
            orientation={orientation}
            selectedSquare={selectedSquare}
            legalTargets={legalTargets}
            highlightedMove={highlightedMove}
            lastMove={lastBoardMove}
            onDrop={requestMove}
            onSquareClick={handleSquareClick}
          />
          {lastMessage ? <div className="quiet-alert">{lastMessage}</div> : null}
        </section>
        <section className="first-move-brief">
          <article className="first-move-card">
            <h1>Premier coup blanc</h1>
          </article>
        </section>
      </main>
    );
  }

  if (appStage === "white-plan-selection" || appStage === "black-plan-selection") {
    const isBlack = appStage === "black-plan-selection";
    return renderShell(
      <main className="plan-selection-shell">
        <div className="plan-selection-topbar">
          <div className="selection-actions">
            <button type="button" onClick={changePlan} className="selection-return-button">
              Retour au choix du camp
            </button>
          </div>
        </div>
        {isBlack ? (
          <section className="plan-selection-board">
            <ChessCoachBoard
              fen={fen}
              boardWidth={Math.min(boardWidth, 220)}
              orientation={orientation}
              selectedSquare={null}
              legalTargets={[]}
              highlightedMove={highlightedMove}
              lastMove={lastBoardMove}
              locked
              onDrop={requestMove}
              onSquareClick={handleSquareClick}
            />
          </section>
        ) : null}
        {plansLoading ? <div className="quiet-alert">Chargement des plans...</div> : null}
        {plansError ? <div className="error-alert">{plansError}</div> : null}
        <OpeningRepertoirePanel
          plans={plans}
          selectedPlanId={selectedPlanId}
          onSelect={handlePlanSelect}
          title={isBlack ? "Reponses noires" : "Ouvertures blanches"}
          mode={isBlack ? "black-reply" : "opening"}
          firstMoveLabel={firstMoveLabel}
        />
      </main>
    );
  }

  return renderShell(
    <main className="coach-live-shell">
      <section className="coach-board-column">
        <div className="coach-board-stage">
          <ChessCoachBoard
            fen={fen}
            boardWidth={boardWidth}
            orientation={orientation}
            selectedSquare={selectedSquare}
            legalTargets={legalTargets}
            highlightedMove={highlightedMove}
            recommendationArrows={recommendationArrows}
            lastMove={lastBoardMove}
            thinking={botThinking}
            onDrop={requestMove}
            onSquareClick={handleSquareClick}
          />

          {checkmateResult ? (
            <div className="checkmate-overlay" role="status" aria-live="polite">
              <span>Echec et mat</span>
              <strong>{checkmateResult.winner} gagnent</strong>
              <p>{checkmateResult.detail}</p>
            </div>
          ) : null}

          {pendingPromotion ? (
            <div className="promotion-popover" role="dialog" aria-label="Choisir une promotion">
              <p>Promotion</p>
              <div>
                {[
                  ["q", "Dame"],
                  ["r", "Tour"],
                  ["b", "Fou"],
                  ["n", "Cavalier"]
                ].map(([piece, label]) => (
                  <button
                    key={piece}
                    type="button"
                    onClick={() => applyMove(pendingPromotion.from, pendingPromotion.to, piece)}
                    className="control-button"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="coach-board-controls">
          <button
            type="button"
            onClick={openImageImport}
            className="control-button icon-control"
            disabled={imageImporting}
            aria-label="Importer une position depuis une image"
            title="Importer une position"
          >
            <ImageUp size={18} />
          </button>
          <button
            type="button"
            onClick={() => runTimelineClick(undo)}
            onTouchEnd={(event) => runTimelineTouch(event, undo)}
            className="control-button icon-control"
            disabled={!canStepBackward}
            aria-disabled={!canStepBackward}
            aria-label="Coup precedent"
            title="Coup precedent"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            onClick={() => runTimelineClick(redo)}
            onTouchEnd={(event) => runTimelineTouch(event, redo)}
            className="control-button icon-control"
            disabled={!canStepForward}
            aria-disabled={!canStepForward}
            aria-label="Coup suivant"
            title="Coup suivant"
          >
            <ChevronRight size={18} />
          </button>
          <button type="button" onClick={reset} className="control-button">Reset</button>
          <button type="button" onClick={() => setOrientation(orientation === "white" ? "black" : "white")} className="control-button">Tourner</button>
        </div>

        <EloLiveIndicator
          baseElo={baseCoachElo}
          currentElo={effectiveCoachElo}
          boost={adaptiveBoost}
          change={eloChange}
          pressureLabel={eloPressureLabel}
        />

        {botError ? <div className="coach-board-error">{botError}</div> : null}
        {lastMessage ? <div className="coach-board-note">{lastMessage}</div> : null}
      </section>

      <section className="coach-panel-column">
        <PlanFirstPanel
          selectedPlan={selectedPlan}
          recommendations={planRecommendations}
          loading={planLoading}
          error={planError}
        />
      </section>
    </main>
  );
}

function EloLiveIndicator({
  baseElo,
  currentElo,
  boost,
  change,
  pressureLabel
}: {
  baseElo: number;
  currentElo: number;
  boost: number;
  change: EloChange | null;
  pressureLabel: string;
}) {
  const direction = change ? (change.delta > 0 ? "up" : "down") : "stable";
  const progress = Math.max(0, Math.min(100, ((currentElo - 600) / (3200 - 600)) * 100));

  return (
    <section className={`elo-live-indicator is-${direction}`} aria-live="polite" aria-label="Elo adaptatif actuel">
      <div className="elo-live-main">
        <span>Niveau actuel</span>
        <strong>{currentElo}</strong>
        {change ? (
          <em key={change.id}>
            {change.delta > 0 ? `+${change.delta}` : change.delta}
          </em>
        ) : null}
      </div>
      <div className="elo-live-track" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="elo-live-meta">
        <span>Base {baseElo}</span>
        <span>{boost > 0 ? `Boost +${boost}` : "Boost 0"}</span>
        <span>{pressureLabel}</span>
      </div>
      {change ? (
        <p key={`change-${change.id}`} className="elo-live-change">
          {change.delta > 0 ? "Le coach augmente le niveau." : "Le coach redescend le niveau."}
        </p>
      ) : (
        <p className="elo-live-change is-quiet">Pas de changement recent.</p>
      )}
    </section>
  );
}

function ImageImportConfirmDialog({
  draft,
  onSideToMoveChange,
  onUserSideChange,
  onProfileChange,
  onOrientationChange,
  onSquareChange,
  onClearBoard,
  onUseCurrentBoard,
  onUseStartingBoard,
  onCancel,
  onConfirm
}: {
  draft: ImageImportDraft;
  onSideToMoveChange: (side: "white" | "black") => void;
  onUserSideChange: (side: "white" | "black") => void;
  onProfileChange: (profile: CoachHumanProfile) => void;
  onOrientationChange: (orientation: Orientation) => void;
  onSquareChange: (square: string, piece: EditablePiece | null) => void;
  onClearBoard: () => void;
  onUseCurrentBoard: () => void;
  onUseStartingBoard: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [selectedPiece, setSelectedPiece] = useState<EditablePiece | null>(null);
  const detectedOrientation = orientationFromBoardOrientation(draft.boardOrientation);
  const editableFen = editableBoardToFen(draft.boardMap, draft.sideToMove);
  const canValidate = editableBoardIsValid(draft.boardMap, draft.sideToMove);
  const statusLabel =
    draft.status === "loading"
      ? "Reconnaissance en cours"
      : draft.status === "local"
        ? "Detection locale"
        : draft.status === "ready"
        ? "Position pre-remplie"
        : "Correction manuelle";

  return (
    <div className="image-import-layer" role="dialog" aria-modal="true" aria-label="Importer une position">
      <button type="button" className="image-import-backdrop" aria-label="Annuler l'import" onClick={onCancel} />
      <section className="image-import-panel">
        <div className="image-import-preview">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={draft.previewUrl} alt="" />
        </div>
        <div className="image-import-content">
          <p className="image-import-eyebrow">{statusLabel}</p>
          <h2>Verifie la position</h2>
          <p className="image-import-copy">Choisis une piece, touche une case pour corriger, puis valide seulement quand le plateau est identique a l&apos;image.</p>
          <div className="image-import-active-tool">
            <span>Outil actif</span>
            <strong>{pieceLabel(selectedPiece)}</strong>
          </div>

          <EditablePositionBoard
            board={draft.boardMap}
            orientation={detectedOrientation}
            selectedPiece={selectedPiece}
            referenceUrl={draft.boardReferenceUrl}
            onSquareChange={onSquareChange}
          />

          <div className="image-import-tools" aria-label="Pieces a placer">
            {EDITABLE_PIECES.map((piece) => (
              <button
                key={piece.label}
                type="button"
                className={selectedPiece === piece.value ? "is-active" : ""}
                onClick={() => setSelectedPiece(piece.value)}
                title={piece.label}
                aria-label={piece.label}
              >
                <span>{piece.symbol}</span>
              </button>
            ))}
          </div>

          <div className="image-import-turn">
            <span>Tu joues</span>
            <div>
              <button
                type="button"
                className={draft.userSide === "white" ? "is-active" : ""}
                onClick={() => onUserSideChange("white")}
              >
                Blancs
              </button>
              <button
                type="button"
                className={draft.userSide === "black" ? "is-active" : ""}
                onClick={() => onUserSideChange("black")}
              >
                Noirs
              </button>
            </div>
          </div>

          <HumanProfileSelector value={draft.humanProfile} onChange={onProfileChange} />

          <div className="image-import-turn">
            <span>Trait</span>
            <div>
              <button
                type="button"
                className={draft.sideToMove === "white" ? "is-active" : ""}
                onClick={() => onSideToMoveChange("white")}
              >
                Blancs
              </button>
              <button
                type="button"
                className={draft.sideToMove === "black" ? "is-active" : ""}
                onClick={() => onSideToMoveChange("black")}
              >
                Noirs
              </button>
            </div>
          </div>

          <div className="image-import-turn">
            <span>Orientation</span>
            <div>
              <button
                type="button"
                className={detectedOrientation === "white" ? "is-active" : ""}
                onClick={() => onOrientationChange("white")}
              >
                Blancs bas
              </button>
              <button
                type="button"
                className={detectedOrientation === "black" ? "is-active" : ""}
                onClick={() => onOrientationChange("black")}
              >
                Noirs bas
              </button>
            </div>
          </div>

          <div className="image-import-quick-actions">
            <button type="button" onClick={onUseCurrentBoard}>Plateau actuel</button>
            <button type="button" onClick={onUseStartingBoard}>Depart</button>
            <button type="button" onClick={onClearBoard}>Vider</button>
          </div>

          {draft.confidence !== null ? (
            <div className="image-import-confidence">
              <span>Confiance auto</span>
              <strong>{draft.confidence}%</strong>
            </div>
          ) : null}

          {draft.message ? <p className="image-import-warning">{draft.message}</p> : null}
          {draft.warnings.length ? (
            <p className="image-import-warning">{draft.warnings[0]}</p>
          ) : null}
          {!canValidate ? (
            <p className="image-import-warning">Position incomplete ou impossible: il faut au minimum une position d&apos;echecs valide avant validation.</p>
          ) : null}

          <div className="image-import-actions">
            <button type="button" className="control-button" onClick={onConfirm} disabled={!canValidate}>
              Valider la position
            </button>
            <button type="button" className="control-button is-muted" onClick={onCancel}>
              Annuler
            </button>
          </div>
          <code className="image-import-fen">{editableFen}</code>
        </div>
      </section>
    </div>
  );
}

function EditablePositionBoard({
  board,
  orientation,
  selectedPiece,
  referenceUrl,
  onSquareChange
}: {
  board: EditableBoard;
  orientation: Orientation;
  selectedPiece: EditablePiece | null;
  referenceUrl: string | null;
  onSquareChange: (square: string, piece: EditablePiece | null) => void;
}) {
  const squares = orientedEditableSquares(orientation);
  return (
    <div
      className={referenceUrl ? "editable-position-board has-reference" : "editable-position-board"}
      aria-label="Position editable"
      style={referenceUrl ? { backgroundImage: `url(${referenceUrl})` } : undefined}
    >
      {squares.map((square) => {
        const fileIndex = EDITABLE_FILES.indexOf(square[0] as (typeof EDITABLE_FILES)[number]);
        const rank = Number(square[1]);
        const isLight = (fileIndex + rank) % 2 === 1;
        const piece = board[square];
        return (
          <button
            key={square}
            type="button"
            className={[
              "editable-square",
              isLight ? "is-light" : "is-dark",
              piece ? "has-piece" : "is-empty"
            ].join(" ")}
            onClick={() => onSquareChange(square, selectedPiece)}
            aria-label={`${square} ${piece ? pieceLabel(piece) : "vide"}`}
            title={`${square} - ${piece ? pieceLabel(piece) : "vide"}`}
          >
            <span>{pieceSymbol(piece)}</span>
            <small>{square}</small>
          </button>
        );
      })}
    </div>
  );
}

function HumanProfileSelector({ value, onChange }: { value: CoachHumanProfile; onChange: (profile: CoachHumanProfile) => void }) {
  const profiles = Object.entries(HUMAN_PROFILE_SETTINGS) as Array<[CoachHumanProfile, (typeof HUMAN_PROFILE_SETTINGS)[CoachHumanProfile]]>;
  return (
    <div className="import-profile-choice" aria-label="Niveau des conseils">
      <span>Niveau conseil</span>
      <div>
        {profiles.map(([id, profile]) => (
          <button key={id} type="button" className={value === id ? "is-active" : ""} onClick={() => onChange(id)} title={profile.description}>
            {profile.shortLabel}
          </button>
        ))}
      </div>
    </div>
  );
}

function FenImportDialog({
  value,
  error,
  userSide,
  profile,
  onValueChange,
  onUserSideChange,
  onProfileChange,
  onPaste,
  onCancel,
  onConfirm
}: {
  value: string;
  error: string | null;
  userSide: "white" | "black";
  profile: CoachHumanProfile;
  onValueChange: (value: string) => void;
  onUserSideChange: (side: "white" | "black") => void;
  onProfileChange: (profile: CoachHumanProfile) => void;
  onPaste: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const previewFen = value.trim() ? normalizeFenInput(value) : null;
  let previewError: string | null = null;
  if (previewFen) {
    try {
      new Chess(previewFen);
    } catch {
      previewError = "Le FEN n'est pas encore valide.";
    }
  }

  return (
    <div className="fen-import-layer" role="dialog" aria-modal="true" aria-label="Importer une position FEN">
      <button type="button" className="fen-import-backdrop" aria-label="Annuler l'import FEN" onClick={onCancel} />
      <section className="fen-import-panel">
        <p className="image-import-eyebrow">Import FEN</p>
        <h2>Colle la position</h2>
        <p className="fen-import-copy">Colle le FEN donne par ChatGPT, Chessvision ou un autre scanner. Le plateau sera reconstruit directement.</p>

        <textarea
          value={value}
          onChange={(event) => onValueChange(event.target.value)}
          placeholder="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
          className="fen-import-textarea"
          rows={5}
          autoFocus
        />

        <div className="image-import-turn">
          <span>Tu joues</span>
          <div>
            <button type="button" className={userSide === "white" ? "is-active" : ""} onClick={() => onUserSideChange("white")}>
              Blancs
            </button>
            <button type="button" className={userSide === "black" ? "is-active" : ""} onClick={() => onUserSideChange("black")}>
              Noirs
            </button>
          </div>
        </div>

        <HumanProfileSelector value={profile} onChange={onProfileChange} />

        {previewFen && !previewError ? (
          <code className="fen-import-preview">{previewFen}</code>
        ) : null}
        {error || previewError ? <p className="image-import-warning">{error ?? previewError}</p> : null}

        <div className="fen-import-actions">
          <button type="button" className="control-button is-muted" onClick={onPaste}>
            Coller
          </button>
          <button type="button" className="control-button" onClick={onConfirm}>
            Importer
          </button>
          <button type="button" className="control-button is-muted" onClick={onCancel}>
            Annuler
          </button>
        </div>
      </section>
    </div>
  );
}

function SiteHeader({
  status,
  menuOpen,
  imageImporting,
  onHome,
  onImportFen,
  onImportImage,
  onToggleMenu
}: {
  status: string | null;
  menuOpen: boolean;
  imageImporting: boolean;
  onHome: () => void;
  onImportFen: () => void;
  onImportImage: () => void;
  onToggleMenu: () => void;
}) {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <button type="button" onClick={onHome} className="site-brand" aria-label="Retour a l'accueil Chess Learning">
          <span className="site-brand-mark" aria-hidden="true">
            <span className="site-brand-pawn" />
          </span>
          <span className="site-brand-text">Chess Learning</span>
        </button>
        <div className="site-header-actions">
          {status ? <span className="site-status">{status}</span> : null}
          <button
            type="button"
            onClick={onImportFen}
            className="site-menu-button site-fen-button"
            aria-label="Importer une position au format FEN"
            title="Importer FEN"
          >
            FEN
          </button>
          <button
            type="button"
            onClick={onImportImage}
            className="site-menu-button"
            aria-label="Importer une position depuis une image"
            title="Importer une position"
            disabled={imageImporting}
          >
            <ImageUp size={19} strokeWidth={2.1} />
          </button>
          <button type="button" onClick={onToggleMenu} className="site-menu-button" aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"} aria-expanded={menuOpen}>
            {menuOpen ? <X size={20} strokeWidth={2.1} /> : <Menu size={20} strokeWidth={2.1} />}
          </button>
        </div>
      </div>
    </header>
  );
}

function SiteMenu({ status, onHome, onClose, children }: { status: string; onHome: () => void; onClose: () => void; children: ReactNode }) {
  return (
    <div className="site-menu-layer">
      <button type="button" className="site-menu-backdrop" aria-label="Fermer le menu" onClick={onClose} />
      <aside className="site-menu-popover" aria-label="Menu Chess Learning">
        <div className="site-menu-head">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-clay">Menu</p>
            <h2 className="text-xl font-semibold text-night">Chess Learning</h2>
          </div>
          <button type="button" onClick={onClose} className="site-menu-close" aria-label="Fermer le menu">
            <X size={18} />
          </button>
        </div>

        <div className="grid gap-2">
          <button type="button" onClick={onHome} className="site-menu-row">
            Accueil
          </button>
          <div className="rounded border border-line bg-stone-50 px-3 py-2 text-sm font-semibold text-neutral-700">{status}</div>
        </div>

        {children}
      </aside>
    </div>
  );
}

function CoachUtilityMenu({
  orientation,
  setOrientation,
  mode,
  setMode,
  undo,
  reset,
  copyFen,
  copyPgn,
  history,
  handleHistoryClick,
  fen,
  pgn,
  historyUci
}: {
  orientation: Orientation;
  setOrientation: (value: Orientation) => void;
  mode: PlayMode;
  setMode: (value: PlayMode) => void;
  undo: () => void;
  reset: () => void;
  copyFen: () => void;
  copyPgn: () => void;
  history: VerboseMove[];
  handleHistoryClick: (ply: number, move: Move) => void;
  fen: string;
  pgn: string;
  historyUci: string[];
}) {
  return (
    <div className="grid gap-4">
      <details open className="site-menu-details">
        <summary className="cursor-pointer text-sm font-semibold text-night">Commandes et reglages</summary>
        <div className="mt-3">
          <GameControls
            orientation={orientation}
            onOrientationChange={setOrientation}
            mode={mode}
            onModeChange={setMode}
            onUndo={undo}
            onReset={reset}
            onCopyFen={copyFen}
            onCopyPgn={copyPgn}
          />
        </div>
      </details>

      <details className="site-menu-details">
        <summary className="cursor-pointer text-sm font-semibold text-night">Historique</summary>
        <div className="mt-3">
          <MoveHistory moves={history} onMoveClick={handleHistoryClick} />
        </div>
      </details>

      <details className="site-menu-details">
        <summary className="cursor-pointer text-sm font-semibold text-night">Details techniques</summary>
        <div className="mt-3 grid gap-2 break-words text-sm text-neutral-700">
          <p>FEN : {fen}</p>
          <p>PGN : {pgn || "*"}</p>
          <p>Coups UCI : {historyUci.join(" ") || "aucun"}</p>
        </div>
      </details>
    </div>
  );
}
