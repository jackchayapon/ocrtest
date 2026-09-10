"use client";
import { messages } from "@/lib/i18n/th";

import { Group, Line, Rect, Text } from "react-konva";
import type { ViewerBox } from "@/types";

interface BoundingBoxLayerProps {
  boxes: ViewerBox[];
  selectedBoxId: string | null;
  onSelectBox: (id: string | null) => void;
  scale: number;
  interactive?: boolean;
}

/** All geometry stays in the original image's coordinate system. */
export default function BoundingBoxLayer({
  boxes,
  selectedBoxId,
  onSelectBox,
  scale,
  interactive = true,
}: BoundingBoxLayerProps) {
  // Draw the selected box last so its outline is never hidden by another pipeline.
  const ordered = [...boxes].sort((a, b) => Number(a.id === selectedBoxId) - Number(b.id === selectedBoxId));

  return (
    <Group listening={interactive}>
      {ordered.map((box) => {
        const [x1, y1, x2, y2] = box.bbox;
        if (![x1, y1, x2, y2].every(Number.isFinite) || x2 <= x1 || y2 <= y1) return null;
        const selected = box.id === selectedBoxId;
        return (
          <Group key={box.id}>
            {selected && (
              <Rect
                x={x1}
                y={y1}
                width={x2 - x1}
                height={y2 - y1}
                stroke="white"
                strokeWidth={7}
                strokeScaleEnabled={false}
                listening={false}
              />
            )}
            <Rect
              name="ocr-box"
              x={x1}
              y={y1}
              width={x2 - x1}
              height={y2 - y1}
              stroke={box.color}
              strokeWidth={selected ? 3 : 1.5}
              strokeScaleEnabled={false}
              fill={box.color}
              opacity={selected ? 1 : 0.8}
              fillEnabled
              fillLinearGradientStartPoint={{ x: 0, y: 0 }}
              fillLinearGradientEndPoint={{ x: 0, y: y2 - y1 }}
              fillLinearGradientColorStops={selected
                ? [0, "rgba(99,102,241,0.12)", 1, "rgba(99,102,241,0.04)"]
                : [0, "rgba(99,102,241,0.015)", 1, "rgba(99,102,241,0.015)"]}
              fillPriority="linear-gradient"
              hitStrokeWidth={10}
              onClick={(event) => {
                event.cancelBubble = true;
                onSelectBox(box.id);
              }}
              onTap={(event) => {
                event.cancelBubble = true;
                onSelectBox(box.id);
              }}
              onMouseEnter={(event) => {
                const container = event.target.getStage()?.container();
                if (container) container.style.cursor = "pointer";
              }}
              onMouseLeave={(event) => {
                const container = event.target.getStage()?.container();
                if (container) container.style.cursor = "";
              }}
            />
            {box.polygon && box.polygon.length >= 3 && <Line name="ocr-box" points={box.polygon.flat()} closed stroke={box.color} strokeWidth={selected ? 3 : 1.5} strokeScaleEnabled={false} fill="rgba(99,102,241,0.04)" onClick={event => { event.cancelBubble = true; onSelectBox(box.id); }} onTap={event => { event.cancelBubble = true; onSelectBox(box.id); }} />}
            {selected && (
              <Text
                x={x1}
                y={Math.max(0, y1 - 21 / scale)}
                text={box.confidence === null ? "Selected result" : messages.confidence(Math.round(box.confidence * 100))}
                fontSize={11 / scale}
                fontStyle="bold"
                padding={3 / scale}
                fill={box.color}
                listening={false}
              />
            )}
          </Group>
        );
      })}
    </Group>
  );
}
