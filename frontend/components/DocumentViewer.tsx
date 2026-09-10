"use client";
import { t } from "@/lib/i18n/th";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Group, Image as KonvaImage, Layer, Rect, Stage } from "react-konva";
import type Konva from "konva";
import { Crop, Hand, LoaderCircle, Maximize, MousePointer2, RotateCcw, ScanLine, Trash2, ZoomIn, ZoomOut } from "lucide-react";
import type { AutoROISuggestion, ROI, ViewerBox } from "@/types";
import AutoROIOverlay from "./AutoROIOverlay";
import BoundingBoxLayer from "./BoundingBoxLayer";
import TestRegionLayer from "./TestRegionLayer";

export interface DocumentViewerProps {
  imageUrl: string;
  width: number;
  height: number;
  roi: ROI | null;
  onRoiChange: (roi: ROI | null) => void;
  boxes: ViewerBox[];
  selectedBoxId: string | null;
  onSelectBox: (id: string | null) => void;
  regionMode: boolean;
  onRegionModeChange: (enabled: boolean) => void;
  suggestions?: AutoROISuggestion[];
  onSelectSuggestion?: (suggestion: AutoROISuggestion) => void;
}

type Point = { x: number; y: number };
type View = Point & { scale: number };
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const MIN_ZOOM = 0.005;
const MAX_ZOOM = 8;

export default function DocumentViewer({
  imageUrl, width, height, roi, onRoiChange, boxes, selectedBoxId,
  onSelectBox, regionMode, onRegionModeChange, suggestions = [], onSelectSuggestion,
}: DocumentViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const drawStartRef = useRef<Point | null>(null);
  const draftRoiRef = useRef<ROI | null>(null);
  const panStartRef = useRef<{ pointer: Point; view: View } | null>(null);
  const [viewport, setViewport] = useState({ width: 600, height: 580 });
  const [storedView, setStoredView] = useState<{ source: string; view: View } | null>(null);
  const [loadedImage, setLoadedImage] = useState<{ url: string; image: HTMLImageElement } | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [panMode, setPanMode] = useState(false);
  const [showBoxes, setShowBoxes] = useState(true);
  const [draftRoi, setDraftRoi] = useState<ROI | null>(null);
  const [pointerCoordinates, setPointerCoordinates] = useState<Point | null>(null);
  const image = loadedImage?.url === imageUrl ? loadedImage.image : undefined;
  const failed = failedUrl === imageUrl;
  const selectedBox = boxes.find((box) => box.id === selectedBoxId);
  const viewSource = `${imageUrl}:${width}:${height}:${viewport.width}:${viewport.height}`;
  const fittedView = useMemo(() => {
    const scale = clamp(Math.min((viewport.width - 64) / width, (viewport.height - 64) / height, 1), MIN_ZOOM, MAX_ZOOM);
    return { scale, x: (viewport.width - width * scale) / 2, y: (viewport.height - height * scale) / 2 };
  }, [width, height, viewport]);
  // Derive the fitted view immediately when a new image or viewport arrives.
  const view = storedView?.source === viewSource ? storedView.view : fittedView;
  const setView = useCallback((next: View | ((current: View) => View)) => {
    setStoredView((current) => ({
      source: viewSource,
      view: typeof next === "function" ? next(current?.source === viewSource ? current.view : fittedView) : next,
    }));
  }, [viewSource, fittedView]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setViewport({
        width: Math.max(1, Math.floor(entry.contentRect.width)),
        height: Math.max(320, Math.floor(entry.contentRect.height)),
      });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    const nextImage = new window.Image();
    nextImage.onload = () => {
      if (!cancelled) {
        drawStartRef.current = null;
        draftRoiRef.current = null;
        panStartRef.current = null;
        setDraftRoi(null);
        setLoadedImage({ url: imageUrl, image: nextImage });
        setFailedUrl(null);
      }
    };
    nextImage.onerror = () => { if (!cancelled) setFailedUrl(imageUrl); };
    nextImage.src = imageUrl;
    return () => {
      cancelled = true;
      nextImage.onload = null;
      nextImage.onerror = null;
    };
  }, [imageUrl, retryKey]);

  const fitView = useCallback(() => { setStoredView(null); }, []);

  const constrainView = useCallback((next: View): View => ({
    scale: next.scale,
    x: width * next.scale <= viewport.width - 40
      ? (viewport.width - width * next.scale) / 2
      : clamp(next.x, viewport.width - width * next.scale - 24, 24),
    y: height * next.scale <= viewport.height - 40
      ? (viewport.height - height * next.scale) / 2
      : clamp(next.y, viewport.height - height * next.scale - 24, 24),
  }), [width, height, viewport]);

  const zoomAt = useCallback((factor: number, point?: Point) => {
    const anchor = point ?? { x: viewport.width / 2, y: viewport.height / 2 };
    setView((current) => {
      const scale = clamp(current.scale * factor, MIN_ZOOM, MAX_ZOOM);
      const original = { x: (anchor.x - current.x) / current.scale, y: (anchor.y - current.y) / current.scale };
      return constrainView({ scale, x: anchor.x - original.x * scale, y: anchor.y - original.y * scale });
    });
  }, [constrainView, viewport, setView]);

  const getOriginalPoint = (): Point | null => {
    const position = stageRef.current?.getPointerPosition();
    if (!position) return null;
    return { x: (position.x - view.x) / view.scale, y: (position.y - view.y) / view.scale };
  };

  function startInteraction(event: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (!image || ("button" in event.evt && event.evt.button !== 0)) return;
    const point = getOriginalPoint();
    const pointer = stageRef.current?.getPointerPosition();
    if (!point || !pointer) return;
    if (regionMode) {
      if (point.x < 0 || point.y < 0 || point.x > width || point.y > height) return;
      const start = { x: clamp(Math.round(point.x), 0, width), y: clamp(Math.round(point.y), 0, height) };
      drawStartRef.current = start;
      draftRoiRef.current = { x1: start.x, y1: start.y, x2: start.x, y2: start.y };
      setDraftRoi(draftRoiRef.current);
      onSelectBox(null);
    } else if (panMode) {
      panStartRef.current = { pointer, view };
    } else if (event.target === event.target.getStage() || event.target.name() === "document-image") {
      onSelectBox(null);
    }
  }

  function moveInteraction() {
    const point = getOriginalPoint();
    const pointer = stageRef.current?.getPointerPosition();
    if (!point || !pointer) return;
    setPointerCoordinates(point.x >= 0 && point.y >= 0 && point.x <= width && point.y <= height
      ? { x: Math.round(point.x), y: Math.round(point.y) } : null);
    if (drawStartRef.current) {
      const start = drawStartRef.current;
      const x = clamp(Math.round(point.x), 0, width);
      const y = clamp(Math.round(point.y), 0, height);
      draftRoiRef.current = { x1: Math.min(start.x, x), y1: Math.min(start.y, y), x2: Math.max(start.x, x), y2: Math.max(start.y, y) };
      setDraftRoi(draftRoiRef.current);
    } else if (panStartRef.current) {
      const start = panStartRef.current;
      setView(constrainView({
        scale: start.view.scale,
        x: start.view.x + pointer.x - start.pointer.x,
        y: start.view.y + pointer.y - start.pointer.y,
      }));
    }
  }

  function finishInteraction() {
    const finalRoi = draftRoiRef.current;
    if (drawStartRef.current && finalRoi && finalRoi.x2 > finalRoi.x1 && finalRoi.y2 > finalRoi.y1) {
      onRoiChange(finalRoi);
      onRegionModeChange(false);
      setPanMode(false);
    }
    drawStartRef.current = null;
    draftRoiRef.current = null;
    panStartRef.current = null;
    setDraftRoi(null);
  }

  const toolClass = (active = false) => `inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${active ? "bg-indigo-100 text-indigo-600" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"} disabled:cursor-not-allowed disabled:opacity-35`;
  const currentRoi = draftRoi ?? roi;

  return (
    <div className="flex min-h-[520px] flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white" data-testid="document-viewer">
      <div className="flex min-h-14 flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <div className="flex items-center gap-1" role="toolbar" aria-label={t("Document tools")}>
          <button type="button" aria-label={t("Select and edit region")} title={t("Select and edit region")} aria-pressed={!panMode && !regionMode} className={toolClass(!panMode && !regionMode)} onClick={() => { setPanMode(false); onRegionModeChange(false); }}><MousePointer2 size={16} /></button>
          <button type="button" aria-label={t("Pan document")} title={t("Pan document")} aria-pressed={panMode && !regionMode} className={toolClass(panMode && !regionMode)} onClick={() => { setPanMode(true); onRegionModeChange(false); }}><Hand size={16} /></button>
          <button type="button" aria-label={t("Draw test region")} title={t("Draw test region")} aria-pressed={regionMode} className={toolClass(regionMode)} onClick={() => { setPanMode(false); onRegionModeChange(!regionMode); }}><Crop size={16} /></button>
          <span className="mx-1 h-5 w-px bg-slate-200" />
          <button type="button" aria-label={showBoxes ? t("Hide OCR boxes") : t("Show OCR boxes")} title={showBoxes ? t("Hide OCR boxes") : t("Show OCR boxes")} aria-pressed={showBoxes} className={toolClass(showBoxes)} onClick={() => setShowBoxes(!showBoxes)}><ScanLine size={16} /></button>
          <button type="button" aria-label={t("Clear test region")} title={t("Clear test region")} disabled={!roi} className={toolClass()} onClick={() => { onRoiChange(null); onRegionModeChange(false); }}><Trash2 size={15} /></button>
        </div>
        <div className="flex items-center gap-1" role="toolbar" aria-label={t("Zoom controls")}>
          <button type="button" aria-label={t("Zoom out")} title={t("Zoom out")} disabled={view.scale <= MIN_ZOOM} className={toolClass()} onClick={() => zoomAt(1 / 1.25)}><ZoomOut size={16} /></button>
          <button type="button" aria-label={t("Zoom to 100 percent")} title={t("Zoom to 100%")} className="min-w-12 rounded-md px-1 py-1.5 text-center font-mono text-xs font-medium text-slate-600 hover:bg-slate-100" onClick={() => zoomAt(1 / view.scale)}>{Math.round(view.scale * 100)}%</button>
          <button type="button" aria-label={t("Zoom in")} title={t("Zoom in")} disabled={view.scale >= MAX_ZOOM} className={toolClass()} onClick={() => zoomAt(1.25)}><ZoomIn size={16} /></button>
          <span className="mx-1 h-5 w-px bg-slate-200" />
          <button type="button" aria-label={t("Fit document to view")} title={t("Fit document to view")} className={toolClass()} onClick={fitView}><Maximize size={15} /></button>
          <button type="button" aria-label={t("Reset document view")} title={t("Reset document view")} className={toolClass()} onClick={() => { fitView(); setPanMode(false); onRegionModeChange(false); }}><RotateCcw size={15} /></button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="relative min-h-[420px] flex-1 overflow-hidden bg-slate-100"
        style={{ height: "clamp(420px, 62vh, 760px)", backgroundImage: "radial-gradient(#cbd5e1 0.7px, transparent 0.7px)", backgroundSize: "16px 16px", cursor: regionMode ? "crosshair" : panMode ? "grab" : "default", touchAction: "none" }}
        tabIndex={0}
        role="group"
        aria-label={t("Document canvas. Use the toolbar to zoom, pan, or draw a test region. Control plus scroll zooms. Escape cancels drawing.")}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            drawStartRef.current = null;
            draftRoiRef.current = null;
            panStartRef.current = null;
            setDraftRoi(null);
            onRegionModeChange(false);
          } else if (event.key === "+" || event.key === "=") {
            event.preventDefault(); zoomAt(1.25);
          } else if (event.key === "-") {
            event.preventDefault(); zoomAt(1 / 1.25);
          } else if (event.key === "0") {
            event.preventDefault(); fitView();
          }
        }}
      >
        {!image && !failed && <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-slate-500" role="status"><LoaderCircle size={17} className="animate-spin" /> {t("Loading document…")}</div>}
        {failed && <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-slate-100 text-sm text-slate-500" role="alert"><span>{t("The document preview could not be loaded.")}</span><button type="button" className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-700" onClick={() => { setFailedUrl(null); setRetryKey((value) => value + 1); }}>{t("Try again")}</button></div>}
        <Stage
          ref={stageRef}
          width={viewport.width}
          height={viewport.height}
          style={{ cursor: regionMode ? "crosshair" : panMode ? "grab" : "default" }}
          onMouseDown={startInteraction}
          onTouchStart={startInteraction}
          onMouseMove={moveInteraction}
          onTouchMove={moveInteraction}
          onMouseUp={finishInteraction}
          onTouchEnd={finishInteraction}
          onMouseLeave={() => { finishInteraction(); setPointerCoordinates(null); }}
          onWheel={(event) => {
            event.evt.preventDefault();
            if (drawStartRef.current || panStartRef.current) return;
            if (event.evt.ctrlKey || event.evt.metaKey) {
              zoomAt(Math.exp(-event.evt.deltaY * 0.005), stageRef.current?.getPointerPosition() ?? undefined);
            } else {
              const unit = event.evt.deltaMode === 1 ? 16 : event.evt.deltaMode === 2 ? viewport.height : 1;
              setView((current) => constrainView({
                ...current,
                x: current.x - (event.evt.shiftKey ? event.evt.deltaY : event.evt.deltaX) * unit,
                y: current.y - (event.evt.shiftKey ? 0 : event.evt.deltaY) * unit,
              }));
            }
          }}
        >
          <Layer>
            {image && <Group x={view.x} y={view.y} scaleX={view.scale} scaleY={view.scale}>
              <Rect width={width} height={height} fill="white" shadowColor="#0f172a" shadowOpacity={0.15} shadowBlur={24} shadowOffsetY={6} listening={false} />
              <KonvaImage name="document-image" image={image} width={width} height={height} />
              {currentRoi && <TestRegionLayer roi={currentRoi} imageWidth={width} imageHeight={height} scale={view.scale} interactive={!regionMode && !panMode && !suggestions.length} drawing={Boolean(draftRoi)} onChange={onRoiChange} />}
              {showBoxes && <BoundingBoxLayer boxes={boxes} selectedBoxId={selectedBoxId} onSelectBox={onSelectBox} scale={view.scale} interactive={!regionMode && !panMode} />}
              {!!suggestions.length && onSelectSuggestion && <AutoROIOverlay suggestions={suggestions} onSelect={onSelectSuggestion} scale={view.scale} interactive={!regionMode && !panMode} />}
            </Group>}
          </Layer>
        </Stage>
        {regionMode && <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-slate-900 px-4 py-2 text-xs font-medium text-white shadow-lg">{t("Drag on the document to select a region")}</div>}
        {selectedBox && !regionMode && <div className="pointer-events-none absolute bottom-4 left-4 right-4 max-h-24 overflow-hidden rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-sm" aria-live="polite"><span className="mr-2 font-semibold" style={{ color: selectedBox.color }}>{t("Selected text")}</span><span className="text-slate-600">{selectedBox.text}</span></div>}
      </div>

      <div className="flex min-h-10 flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-white px-3 py-2 text-[10px] text-slate-400">
        <span className="font-mono">{width.toLocaleString()} × {height.toLocaleString()} px{pointerCoordinates && <span className="ml-3">x {pointerCoordinates.x} · y {pointerCoordinates.y}</span>}</span>
        {roi ? <span className="font-mono text-indigo-500" aria-live="polite">{t("ROI (")}{roi.x1}, {roi.y1}) — ({roi.x2}, {roi.y2}) · {roi.x2 - roi.x1} × {roi.y2 - roi.y1} px</span> : <span>{t("Scroll to move · Ctrl + scroll to zoom")}</span>}
      </div>
    </div>
  );
}
