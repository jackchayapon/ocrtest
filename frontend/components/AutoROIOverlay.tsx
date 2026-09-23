import { useState } from "react";
import { messages } from "@/lib/i18n/th";
import { Group, Rect, Text } from "react-konva";
import type { AutoROISuggestion } from "@/types";

export default function AutoROIOverlay({ suggestions, onSelect, scale, interactive, activeId }: { suggestions: AutoROISuggestion[]; onSelect: (suggestion: AutoROISuggestion) => void; scale: number; interactive: boolean; activeId?: string | null }) {
  const [hovered, setHovered] = useState<string | null>(null);
  return <Group listening={interactive}>{suggestions.map((suggestion, index) => <Group key={suggestion.id}><Rect name="auto-roi" x={suggestion.roi.x1} y={suggestion.roi.y1} width={suggestion.roi.x2 - suggestion.roi.x1} height={suggestion.roi.y2 - suggestion.roi.y1} stroke={activeId === suggestion.id ? "#6256df" : hovered === suggestion.id ? "#0e7490" : "#0891b2"} strokeWidth={activeId === suggestion.id || hovered === suggestion.id ? 2.5 : 1.5} strokeScaleEnabled={false} dash={activeId === suggestion.id ? undefined : [6 / scale, 4 / scale]} fill={hovered === suggestion.id ? "rgba(8,145,178,0.18)" : "rgba(8,145,178,0.04)"} listening={activeId !== suggestion.id} onMouseEnter={() => setHovered(suggestion.id)} onMouseLeave={() => setHovered(null)} onClick={e => { e.cancelBubble = true; onSelect(suggestion); }} onTap={e => { e.cancelBubble = true; onSelect(suggestion); }} /><Text x={suggestion.roi.x1} y={Math.max(0, suggestion.roi.y1 - 17 / scale)} text={`${messages.suggestion(index + 1)}${activeId === suggestion.id ? " · เลือกอยู่" : ""}`} fontSize={10 / scale} fill="#0891b2" listening={false} /></Group>)}</Group>;
}
