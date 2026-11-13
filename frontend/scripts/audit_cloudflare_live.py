#!/usr/bin/env python3
"""
Earth Pulse SAR — Cloudflare Live Public Audit
Performs read-only functional inspection of the public Cloudflare tunnel:
  https://integrating-telephone-wise-newman.trycloudflare.com
across all six pages, collecting console errors, network statuses, DOM elements, and UI interactions.
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any, List
import websockets

TARGET_URL = "https://integrating-telephone-wise-newman.trycloudflare.com"

class LiveAuditor:
    def __init__(self, port=9333):
        self.port = port
        self.proc = None
        self.temp_dir = tempfile.mkdtemp(prefix="ep_audit_")
        self.ws: Optional[Any] = None
        self._msg_id = 0
        self.console_logs = []
        self.network_failures = []
        self.audit_results = {}

    def start(self):
        cmd = [
            "chromium",
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.temp_dir}",
            "about:blank",
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.2)

    async def connect(self):
        targets_url = f"http://127.0.0.1:{self.port}/json"
        for _ in range(25):
            try:
                with urllib.request.urlopen(targets_url, timeout=1.0) as resp:
                    targets = json.loads(resp.read().decode())
                    if targets:
                        page_target = next((t for t in targets if t.get("type") == "page"), targets[0])
                        ws_url = page_target.get("webSocketDebuggerUrl")
                        if ws_url:
                            self.ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
                            await self.send("Page.enable")
                            await self.send("Runtime.enable")
                            await self.send("Console.enable")
                            await self.send("Log.enable")
                            await self.send("Network.enable")
                            # Set viewport to 1440x900
                            await self.send("Emulation.setDeviceMetricsOverride", {
                                "width": 1440,
                                "height": 900,
                                "deviceScaleFactor": 1,
                                "mobile": False,
                            })
                            return
            except Exception:
                await asyncio.sleep(0.3)
        raise RuntimeError(f"Could not connect to Chromium CDP on port {self.port}")

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("Chromium WebSocket connection has not been initialized.")
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))

        while True:
            resp_raw = await self.ws.recv()
            resp = json.loads(resp_raw)

            # Record async events
            method_evt = resp.get("method")
            if method_evt == "Console.messageAdded":
                msg_obj = resp.get("params", {}).get("message", {})
                self.console_logs.append(msg_obj)
            elif method_evt == "Network.responseReceived":
                resp_data = resp.get("params", {}).get("response", {})
                status = resp_data.get("status", 200)
                url = resp_data.get("url", "")
                if status >= 400 and "trycloudflare.com/api" in url:
                    self.network_failures.append({"url": url, "status": status})

            if resp.get("id") == self._msg_id:
                return resp

    async def navigate(self, url: str, settle_seconds=3.0):
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(settle_seconds)

    async def evaluate(self, expression: str):
        res = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return res.get("result", {}).get("result", {}).get("value")

    async def close(self):
        if self.ws:
            await self.ws.close()
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        subprocess.run(["rm", "-rf", self.temp_dir], check=False)


async def run_live_audit():
    auditor = LiveAuditor(port=9333)
    auditor.start()
    report = {}

    try:
        await auditor.connect()
        print("Connected to headless Chromium auditor")

        # -------------------------------------------------------------
        # 1. AUDIT PAGE 1: DASHBOARD (/)
        # -------------------------------------------------------------
        print("\n--- Auditing Page 1: Dashboard (/) ---")
        await auditor.navigate(f"{TARGET_URL}/", settle_seconds=3.5)
        dash_data = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            const heroTitle = document.querySelector('.hero-heading')?.innerText || '';
            const runCards = Array.from(document.querySelectorAll('.campaign-card, .card')).map(c => c.innerText);
            const kpiItems = Array.from(document.querySelectorAll('.kpi-card, .stat-card')).map(k => k.innerText);
            const runSelect = document.querySelector('.header-run-select')?.value || '';
            return {
                title: document.title,
                heroTitle,
                has2024: body.includes('+5.8432') || body.includes('5.8432'),
                has2025: body.includes('+1.0440') || body.includes('1.0440'),
                selectedRun: runSelect,
                bodySnippet: body.slice(0, 400),
            };
        })()""")
        report["page_1_dashboard"] = dash_data
        print("Dashboard status:", dash_data)

        # -------------------------------------------------------------
        # 2. AUDIT PAGE 2: SATELLITE MAP EXPLORER (/explorer)
        # -------------------------------------------------------------
        print("\n--- Auditing Page 2: Satellite Map Explorer (/explorer) ---")
        await auditor.navigate(f"{TARGET_URL}/explorer", settle_seconds=4.0)

        explorer_data = await auditor.evaluate("""(() => {
            const mapEl = document.querySelector('.leaflet-map-canvas');
            const tileLayers = Array.from(document.querySelectorAll('.leaflet-tile-pane img')).map(img => img.src);
            const basemapSelect = document.querySelector('#basemap-mode-select');
            const layerButtons = Array.from(document.querySelectorAll('.layer-btn')).map(b => b.innerText.trim());
            const opacitySlider = document.querySelector('.layer-slider');
            const focusBtn = document.querySelector('.btn-focus-aoi');
            const coordsBadge = document.querySelector('.map-coords-badge')?.innerText || '';
            const legendEl = document.querySelector('.map-legend-dock');

            return {
                hasCanvas: Boolean(mapEl),
                canvasW: mapEl ? mapEl.clientWidth : 0,
                canvasH: mapEl ? mapEl.clientHeight : 0,
                tilesLoaded: tileLayers.length,
                sampleTileUrl: tileLayers[0] || null,
                layerButtons,
                hasOpacitySlider: Boolean(opacitySlider),
                hasFocusBtn: Boolean(focusBtn),
                coordsBadge,
                hasLegend: Boolean(legendEl),
            };
        })()""")

        # Test clicking layer buttons
        await auditor.evaluate("""(() => {
            const btns = document.querySelectorAll('.layer-btn');
            if (btns.length > 1) {
                btns[1].click(); // Click second layer (water mask)
            }
        })()""")
        await asyncio.sleep(1.0)

        # Test switching campaign in header to 2024
        await auditor.evaluate("""(() => {
            const sel = document.querySelector('.header-run-select');
            if (sel) {
                sel.value = 'run_20261110_221732_1f2e94';
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        })()""")
        await asyncio.sleep(2.0)

        explorer_2024_data = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            return {
                has2024Metric: body.includes('+5.8432') || body.includes('5.8432'),
                hasLegacyNotice: body.includes('correspondence quality not evaluated') || body.includes('legacy'),
            };
        })()""")

        report["page_2_explorer"] = {
            "initial_state": explorer_data,
            "campaign_2024_switch": explorer_2024_data,
        }
        print("Explorer status:", report["page_2_explorer"])

        # -------------------------------------------------------------
        # 3. AUDIT PAGE 3: NEW SATELLITE ANALYSIS (/new-analysis)
        # -------------------------------------------------------------
        print("\n--- Auditing Page 3: New Satellite Analysis (/new-analysis) ---")
        await auditor.navigate(f"{TARGET_URL}/new-analysis", settle_seconds=3.0)

        new_analysis_data = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            const boxBtn = document.querySelector('.btn-draw-box');
            const polyBtn = document.querySelector('.btn-draw-poly');
            const demoBtn = document.querySelector('.btn-preset-aoi');
            const clearBtn = document.querySelector('.btn-clear-aoi');
            const searchBtn = document.querySelector('.btn-search-catalog');
            const presetMonsoon = Array.from(document.querySelectorAll('.btn-preset')).find(b => b.innerText.includes('Monsoon'));
            const presetJan = Array.from(document.querySelectorAll('.btn-preset')).find(b => b.innerText.includes('January'));

            return {
                hasBoxBtn: Boolean(boxBtn),
                hasPolyBtn: Boolean(polyBtn),
                hasDemoBtn: Boolean(demoBtn),
                hasClearBtn: Boolean(clearBtn),
                hasSearchBtn: Boolean(searchBtn),
                hasPresetMonsoon: Boolean(presetMonsoon),
                hasPresetJan: Boolean(presetJan),
                bodyPreview: body.slice(0, 300),
            };
        })()""")

        # Test clicking Demo Reach
        await auditor.evaluate("""(() => {
            const demoBtn = document.querySelector('.btn-preset-aoi');
            if (demoBtn) demoBtn.click();
        })()""")
        await asyncio.sleep(1.0)

        # Test clicking "Search Satellite Data"
        print("Testing catalogue search button...")
        await auditor.evaluate("""(() => {
            const searchBtn = document.querySelector('.btn-search-catalog');
            if (searchBtn) searchBtn.click();
        })()""")

        # Wait for search results
        for _ in range(25):
            has_results = await auditor.evaluate("""(() => {
                const body = document.body.innerText;
                return body.includes('Satellite Catalogue Matches') || body.includes('Total Scenes:');
            })()""")
            if has_results:
                break
            await asyncio.sleep(0.5)

        catalog_results = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            const dropdown = document.querySelector('.pair-dropdown');
            const detailCard = document.querySelector('.pair-detail-card');
            const submitBtn = document.querySelector('.btn-submit-job');
            return {
                hasMatchesTitle: body.includes('Satellite Catalogue Matches'),
                hasScenesCount: body.includes('Total Scenes:'),
                hasPairsCount: body.includes('Compatible Pairs:'),
                dropdownOptions: dropdown ? dropdown.options.length : 0,
                hasDetailCard: Boolean(detailCard),
                hasSubmitBtn: Boolean(submitBtn),
            };
        })()""")

        # Test clicking Submit Request (verifying demo-mode protection)
        print("Testing submit button demo protection...")
        await auditor.evaluate("""(() => {
            const submitBtn = document.querySelector('.btn-submit-job');
            if (submitBtn) submitBtn.click();
        })()""")
        await asyncio.sleep(2.0)

        demo_protection_check = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            return {
                hasProtectionCard: body.includes('Public Demo Mode: Compute Protection Active'),
                hasCampaignLinks: body.includes('Explore 2025 Live SAR Run') || body.includes('Explore 2024 Monsoon Baseline'),
            };
        })()""")

        report["page_3_new_analysis"] = {
            "initial_state": new_analysis_data,
            "catalog_results": catalog_results,
            "demo_protection": demo_protection_check,
        }
        print("New Analysis status:", report["page_3_new_analysis"])

        # -------------------------------------------------------------
        # 4. AUDIT PAGE 4: FLOOD COMPARISON (/comparison)
        # -------------------------------------------------------------
        print("\n--- Auditing Page 4: Flood Comparison (/comparison) ---")
        await auditor.navigate(f"{TARGET_URL}/comparison", settle_seconds=3.0)

        comp_data = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            const maps = document.querySelectorAll('.leaflet-map-canvas');
            const syncSwitch = document.querySelector('.toggle-sync, input[type=\"checkbox\"]');
            return {
                title: body.includes('Dual-Epoch') || body.includes('Flood Comparison'),
                mapCanvases: maps.length,
                hasT1: body.includes('T1 BASELINE'),
                hasT2: body.includes('T2 OBSERVATION'),
                hasTransitionsTable: body.includes('Newly Inundated') && body.includes('Receded Water'),
                hasMorphoGate: body.includes('Morphodynamics') || body.includes('Bank Migration'),
                netChangeConfirmed: body.includes('+1.0440') || body.includes('+5.8432'),
            };
        })()""")
        report["page_4_comparison"] = comp_data
        print("Comparison status:", comp_data)

        # -------------------------------------------------------------
        # 5. AUDIT PAGE 5: EXPLAINABLE AI (/explainable-ai)
        # -------------------------------------------------------------
        print("\n--- Auditing Page 5: Explainable AI (/explainable-ai) ---")
        await auditor.navigate(f"{TARGET_URL}/explainable-ai", settle_seconds=3.0)

        xai_data = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            return {
                hasFormula: body.includes('f(x)') || body.includes('base') || body.includes('Saabas'),
                has40Trees: body.includes('40') && (body.includes('tree') || body.includes('trees')),
                hasTreePathTerminology: body.includes('tree-path') || body.includes('attribution'),
                hasAdditivityBadge: body.includes('Additivity Verified') || body.includes('Verified'),
                hasNaN: body.includes('NaN'),
                hasFeaturesList: body.includes('VV') && body.includes('VH'),
            };
        })()""")
        report["page_5_explainable_ai"] = xai_data
        print("XAI status:", xai_data)

        # -------------------------------------------------------------
        # 6. AUDIT PAGE 6: SCIENCE & METHODOLOGY (/science)
        # -------------------------------------------------------------
        print("\n--- Auditing Page 6: Science & Methodology (/science) ---")
        await auditor.navigate(f"{TARGET_URL}/science", settle_seconds=2.5)

        sci_data = await auditor.evaluate("""(() => {
            const body = document.body.innerText;
            return {
                hasSarPhysics: body.includes('C-Band SAR Microwave Physics'),
                hasSnapCalibration: body.includes('ESA SNAP Calibration'),
                hasLeeFilter: body.includes('Refined Lee Filter'),
                hasWaterClass: body.includes('Otsu') || body.includes('Water Classification'),
                hasMorpho: body.includes('Riverbank Morphodynamics'),
                hasSaabas: body.includes('Saabas Explainable AI'),
                hasProviders: body.includes('European Space Agency') || body.includes('NASA ASF'),
            };
        })()""")
        report["page_6_science"] = sci_data
        print("Science status:", sci_data)

        # Collect console issues and network errors
        report["console_logs_count"] = len(auditor.console_logs)
        report["console_errors"] = [l for l in auditor.console_logs if l.get("level") == "error"]
        report["network_failures"] = auditor.network_failures

        # Write final audit report to JSON
        out_path = Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/CLOUDFLARE_LIVE_AUDIT_REPORT.json")
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nAudit complete! Detailed report written to {out_path}")

    finally:
        await auditor.close()

if __name__ == "__main__":
    asyncio.run(run_live_audit())

