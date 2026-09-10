import { messages } from "@/lib/i18n/th";
import { Group, Rect, Text } from "react-konva";
import type { AutoROISuggestion } from "@/types";

export default function AutoROIOverlay({ suggestions, onSelect, scale, interactive }: { suggestions: AutoROISuggestion[]; onSelect: (suggestion: AutoROISuggestion) => void; scale: number; interactive: boolean }) {
  return <Group listening={interactive}>{suggestions.map((suggestion, index) => <Group key={suggestion.id}><Rect name="auto-roi" x={suggestion.roi.x1} y={suggestion.roi.y1} width={suggestion.roi.x2 - suggestion.roi.x1} height={suggestion.roi.y2 - suggestion.roi.y1} stroke="#0891b2" strokeWidth={1.5} strokeScaleEnabled={false} dash={[6 / scale, 4 / scale]} fill="rgba(8,145,178,0.06)" onClick={e => { e.cancelBubble = true; onSelect(suggestion); }} onTap={e => { e.cancelBubble = true; onSelect(suggestion); }} /><Text x={suggestion.roi.x1} y={Math.max(0, suggestion.roi.y1 - 17 / scale)} text={messages.suggestion(index + 1)} fontSize={10 / scale} fill="#0891b2" listening={false} /></Group>)}</Group>;
}
