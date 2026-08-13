---
id: EXTDATA-AKSHARE-R1
title: Zero-cost external fundamental/news-risk data feasibility via AkShare
code_name: AkShare External Data Exploration
status: DRAFT
risk: MEDIUM
owner: Claude
created_at: 2026-08-13T14:00:00+08:00
updated_at: 2026-08-13T14:00:00+08:00
---

## Goal

Evaluate whether AkShare can serve as a zero-cost, structured, point-in-time historical
source for fundamental line items and/or news-risk signals covering the official 49 stocks
and 6 sectors, without purchasing paid APIs or violating source terms.

## Scope

- Research-only; no production, direct/formal/RPC/E2E, model call, credential use, or
  report/submission claim.
- Focus on publicly available AkShare endpoints that expose historical fundamental data
  (income statement, balance sheet, cash flow) and news/announcement event data for A-shares.
- Establish whether the source provides: ticker coverage, period/taxonomy, publication or
  observed-at timestamp, revision/correction lineage, and cross-device reproducibility.
- Produce a provider-admission recommendation: `AVAILABLE`, `AVAILABLE_WITH_GAPS`, or
  `REJECTED`.

## Non-goals

- No implementation of a production Provider or Factor until admission is accepted by Codex.
- No paid API usage within this task (Tushare or other vendors are out of scope here).
- No LLM-generated facts, PDF scraping, or keyword-only announcement matching.

## Success criteria

1. Enumerate AkShare endpoints relevant to the 49 official tickers.
2. Fetch a small historical sample and verify 49/49 coverage for at least one endpoint.
3. Document schema, timestamp semantics, revision behavior and missing-field handling.
4. Compute content hashes and assess cross-device reproducibility.
5. Write a focused admission report with evidence refs; do not promote to `BUSINESS_PASSED`
   without Codex review.

## Blocked by

- WP1-E4-R1 must reach `CLOSED` status before this task moves out of `DRAFT`.
