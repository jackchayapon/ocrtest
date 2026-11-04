import { expect, test } from "@playwright/test";
import { userError } from "../lib/i18n/th";

test("model-worker 422 gives an actionable upstream message", () => {
  const message = userError("Gateway model worker failed; verify the model service using the request ID", 422);
  expect(message).toContain("ทีมดูแลโมเดล");
  expect(message).toContain("Gateway Request ID");
  expect(message).not.toContain("ข้อมูลไม่ถูกต้อง");
});

test("partial field failure preserves the explanation of saved successes", () => {
  expect(userError("One or more fields failed; successful field predictions remain available"))
    .toContain("ผลของพื้นที่ที่สำเร็จยังถูกบันทึกไว้");
});

test("ordinary validation and authentication remain distinct", () => {
  expect(userError("Invalid value", 422)).toContain("ข้อมูลไม่ถูกต้อง");
  expect(userError("Gateway authentication is required", 401)).toContain("API Key");
});
