import {defineConfig} from "@playwright/test";
import config from "./playwright.config";

// Explicit local integration entry point. Start all three services and set the
// approved loopback provider before running this separately from mock UI tests.
export default defineConfig({...config, testMatch: "external-live.integration.ts", timeout: 90_000});
