# FlowBooks 2.21.0

Free standalone bookkeeping for your own computer, company and password. The app download does not require a Level9 account or payment. A separately written connector may have separate commercial terms; it contains no FlowBooks code, templates or assets.

This is a clean source staging export. Public installer downloads are not published yet. Reviewed release downloads will be listed at [Releases](https://github.com/ceember/FlowBooks/releases).

1. Choose the package for your computer. The prepared Mac package targets Apple Silicon **arm64 and macOS 26.0 or later**. It is ad-hoc signed, **not Developer ID signed or notarized**; this is not a claim of support for Intel Macs or older macOS. Windows x64 packaging is included in source, but the **unsigned Windows installer is NOT_BUILT and installation/GUI behavior is NOT_TESTED**.
2. For a reviewed Mac release, open the DMG and copy FlowBooks.app to Applications, or extract the app from the ZIP. Open FlowBooks and create your own new company.
3. Set your own password in ordinary first-run setup. A newly created company defaults to **ZAR (rand)**; **USD** is a visible first-run choice before recording transactions. Saved currency in existing books is preserved. Changing a label does not convert ledger amounts.
4. Keep your company files and backups private on your computer. Do not upload them to this source repository or put passwords/tokens into issue reports.
5. Download the release's complete LICENSE and SHA256 checksums with the app. A release or source preparation does not certify your tax/payroll filings or currency conversion.

Compatibility: the existing data path is retained, including `~/Library/Application Support/SlowBooksPro/data` on Mac and `%LOCALAPPDATA%\SlowBooksPro\data` on Windows. A renamed installer does **not** establish a separate default data directory from an upstream SlowBooks installation. Close FlowBooks before Windows upgrades or uninstallation. The installer source removes global process-name force-stop hooks and retains standard files-in-use handling. This staging delivery does not transfer, replace or convert populated books. The unchanged launcher runs normal schema migrations when a company is opened; the shared data location can therefore expose existing books to that behavior. Use a new company for first-run evaluation, preserve backups and review co-install compatibility before opening existing company files.

The code includes US payroll/tax forms, rates, identifiers and banking assumptions, as well as some US/USD document defaults. General bookkeeping and a ZAR/USD first-run choice do not establish South African or Zimbabwean statutory payroll/VAT compliance. ZiG's ISO code is ZWG; ZWG selection, reports and exchange-rate behavior are not validated by this staging export. No paid provider or FX service is required or configured by these installation instructions.

Native Windows build inputs are in `.github/workflows/windows.yml` and `packaging/windows/`. The manual workflow uses standard public Windows hosted runners, CPython 3.12, MSYS2 DLLs, PyInstaller and Inno Setup, with no signing account. It stores candidate assets in **draft Releases for authenticated owner review**, rather than Actions artifact/cache storage, and does not automatically publish a public release. The included validation script proposes normal synthetic company/password/ZAR/USD/business-PDF/restart and quiet-install checks; those checks are **NOT_RUN**. Headless HTTP/PDF text and silent-install evidence cannot prove native GUI, PDF viewer or installer-wizard journeys. This staging task has not run a build, app test, workflow or deployment.

[Source Available License, version 2.0](LICENSE) governs the renamed derivative; this is **not an MIT-licensed distribution**. Redistribution is free, with the full license/copyright and acknowledgment retained. Separate programs that only interoperate through the permitted API/file interfaces, without incorporating the software's code, are addressed by section 2(d).

**SlowBooks Pro 2026 — originally created by Trent Von Holten**

Copyright (c) 2026 Trent Von Holten. Derived from [SlowBooks Pro 2026 v2.21.0](https://github.com/VonHoltenCodes/SlowBooks-Pro-2026/tree/496f2ae5b06a03bf0c1299e21cc71c3670a4e46e), with FlowBooks customization. The licensor's name is attribution, not endorsement of this fork.
