import { describe, expect, test } from "vitest";
import { formatElapsedTime } from "./elapsed";

describe("admin elapsed timer", () => {
  test("formats minutes and seconds with stable two-digit padding", () => {
    expect(formatElapsedTime(0)).toBe("00:00");
    expect(formatElapsedTime(9)).toBe("00:09");
    expect(formatElapsedTime(65)).toBe("01:05");
    expect(formatElapsedTime(3661)).toBe("61:01");
  });

  test("does not render negative or fractional time", () => {
    expect(formatElapsedTime(-4)).toBe("00:00");
    expect(formatElapsedTime(12.9)).toBe("00:12");
  });
});
