"use client";
import { t } from "@/lib/i18n/th";

import { useEffect, useRef } from "react";
import { Group, Rect, Text, Transformer } from "react-konva";
import type Konva from "konva";
import type { ROI } from "@/types";

interface TestRegionLayerProps {
  roi: ROI;
  imageWidth: number;
  imageHeight: number;
  scale: number;
  interactive: boolean;
  drawing?: boolean;
  onChange: (roi: ROI) => void;
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export default function TestRegionLayer({
  roi,
  imageWidth,
  imageHeight,
  scale,
  interactive,
  drawing = false,
  onChange,
}: TestRegionLayerProps) {
  const shapeRef = useRef<Konva.Rect>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const regionWidth = roi.x2 - roi.x1;
  const regionHeight = roi.y2 - roi.y1;

  useEffect(() => {
    if (interactive && shapeRef.current && transformerRef.current) {
      transformerRef.current.nodes([shapeRef.current]);
      transformerRef.current.getLayer()?.batchDraw();
    }
  }, [interactive, roi]);

  function commitShape() {
    const shape = shapeRef.current;
    if (!shape) return;
    const nextWidth = clamp(Math.round(shape.width() * shape.scaleX()), 1, imageWidth);
    const nextHeight = clamp(Math.round(shape.height() * shape.scaleY()), 1, imageHeight);
    const x1 = clamp(Math.round(shape.x()), 0, imageWidth - nextWidth);
    const y1 = clamp(Math.round(shape.y()), 0, imageHeight - nextHeight);
    // Konva transforms scale; persisted ROI dimensions must never include that scale.
    shape.scale({ x: 1, y: 1 });
    shape.position({ x: x1, y: y1 });
    shape.size({ width: nextWidth, height: nextHeight });
    onChange({ x1, y1, x2: x1 + nextWidth, y2: y1 + nextHeight });
  }

  return (
    <Group>
      <Group listening={false} opacity={0.16}>
        <Rect x={0} y={0} width={imageWidth} height={roi.y1} fill="#0f172a" />
        <Rect x={0} y={roi.y2} width={imageWidth} height={Math.max(0, imageHeight - roi.y2)} fill="#0f172a" />
        <Rect x={0} y={roi.y1} width={roi.x1} height={regionHeight} fill="#0f172a" />
        <Rect x={roi.x2} y={roi.y1} width={Math.max(0, imageWidth - roi.x2)} height={regionHeight} fill="#0f172a" />
      </Group>
      <Rect
        ref={shapeRef}
        name="test-region"
        x={roi.x1}
        y={roi.y1}
        width={regionWidth}
        height={regionHeight}
        stroke="#6366f1"
        strokeWidth={2}
        strokeScaleEnabled={false}
        dash={drawing ? [6 / scale, 4 / scale] : undefined}
        fill="rgba(99,102,241,0.035)"
        draggable={interactive}
        listening={interactive}
        dragBoundFunc={(position) => {
          const parent = shapeRef.current?.getParent();
          if (!parent) return position;
          const absoluteTransform = parent.getAbsoluteTransform();
          const local = absoluteTransform.copy().invert().point(position);
          return absoluteTransform.point({
            x: clamp(local.x, 0, imageWidth - regionWidth),
            y: clamp(local.y, 0, imageHeight - regionHeight),
          });
        }}
        onMouseDown={(event) => { event.cancelBubble = true; }}
        onTouchStart={(event) => { event.cancelBubble = true; }}
        onDragEnd={(event) => {
          event.cancelBubble = true;
          commitShape();
        }}
        onTransformEnd={commitShape}
      />
      <Text
        x={roi.x1 + 7 / scale}
        y={roi.y1 + 7 / scale}
        text={t("TEST REGION")}
        fontFamily="Tahoma, sans-serif"
        fontSize={10 / scale}
        fontStyle="bold"
        letterSpacing={0}
        fill="#4f46e5"
        listening={false}
        visible={regionWidth * scale > 110 && regionHeight * scale > 35}
      />
      {interactive && (
        <Transformer
          ref={transformerRef}
          rotateEnabled={false}
          flipEnabled={false}
          keepRatio={false}
          ignoreStroke
          borderEnabled={false}
          anchorSize={9}
          anchorCornerRadius={2}
          anchorFill="white"
          anchorStroke="#6366f1"
          anchorStrokeWidth={1.5}
          padding={0}
          boundBoxFunc={(oldBox, newBox) => {
            const parent = shapeRef.current?.getParent();
            if (!parent) return oldBox;
            const transform = parent.getAbsoluteTransform();
            const topLeft = transform.point({ x: 0, y: 0 });
            const bottomRight = transform.point({ x: imageWidth, y: imageHeight });
            const epsilon = 0.01;
            if (
              newBox.width < scale || newBox.height < scale ||
              newBox.x < topLeft.x - epsilon || newBox.y < topLeft.y - epsilon ||
              newBox.x + newBox.width > bottomRight.x + epsilon ||
              newBox.y + newBox.height > bottomRight.y + epsilon
            ) return oldBox;
            return newBox;
          }}
        />
      )}
    </Group>
  );
}
