# Sahyadri Precision Components Pvt. Ltd.
## Corporate Finance & Procurement Standard Operating Procedure (SOP)
**Document Reference:** SOP-FIN-PROC-2025-V1  
**Effective Date:** 01-April-2025  
**Review Cycle:** Annual  
**Applicability:** All Manufacturing Plants (Chakan Units I & II), Engineering Centers, and Corporate Offices  

---

### Section 1: Purpose, Scope, and Accounting Governance
- **Clause 1.1: Purpose and Objectives**  
  This Standard Operating Procedure defines the corporate financial delegation of authorities, expenditure approval workflows, internal control mechanisms, and statutory compliance protocols for Sahyadri Precision Components Pvt. Ltd. The primary objective is to safeguard corporate assets, maintain rigorous compliance under the Companies Act 2013 and Central Goods and Services Tax (CGST) Act 2017, and eliminate fraudulent procurement or disbursement practices.

- **Clause 1.2: Scope and Boundary**  
  This policy governs all financial transactions, purchase commitments, supplier contracts, journal vouchers, invoice verifications, and general ledger disbursements initiated across all operating departments, including Finance, Procurement, Production, Maintenance, Quality Assurance, and Information Technology.

- **Clause 1.3: Custodianship and Enforcement**  
  The Chief Financial Officer (CFO) and the Head of Internal Audit maintain joint custodianship over this policy. Compliance is mandatory for all personnel. Any deliberate evasion or override of these controls constitutes gross professional misconduct subject to immediate suspension, disciplinary review, and potential legal remedies.

- **Clause 1.4: Accounting Standards Parity**  
  All accounting records must strictly follow Indian Accounting Standards (Ind AS) and the principles of double-entry bookkeeping. For every general ledger posting, total debits must exactly equal total credits across all account codes.

---

### Section 2: Financial Delegated Authority Matrix and Approval Tiers
- **Clause 2.1: Tier 1 - Department Manager Approval (Up to Rs 50,000)**  
  Operating expenses, consumable tooling purchases, routine plant maintenance items, and logistics charges up to and including INR 50,000 (Rupees Fifty Thousand only) may be approved by designated Department Managers (Finance, Procurement, Operations, IT) within their pre-approved operational cost centers.

- **Clause 2.2: Tier 2 - Finance Head Approval (Above Rs 50,000 up to Rs 10,00,000)**  
  Any expenditure, purchase order amendment, service contract, or disbursement exceeding INR 50,000 and up to INR 10,00,000 (Rupees Ten Lakhs only) strictly mandates secondary verification and approval from the Finance Head / Controller.

- **Clause 2.3: Tier 3 - Chief Financial Officer Approval (Above Rs 10,00,000)**  
  All major procurement commitments, capital expenditures (CAPEX), strategic raw material contracts, bank debt operations, and journal entries exceeding INR 10,00,000 (Rupees Ten Lakhs only) mandate explicit written authorization and electronic signature from the Chief Financial Officer (CFO).

- **Clause 2.4: Absence and Temporary Delegation**  
  During statutory leaves of absence, financial approval authorities may only be delegated in writing to an officer of equal or higher seniority, pre-registered with the Internal Audit Division. Downward delegation below specified authority bands is prohibited.

---

### Section 3: Segregation of Duties (SoD) and Conflict of Interest Controls
- **Clause 3.1: Strict Segregation of Preparer and Approver (No Self-Approval)**  
  Under no circumstances may any officer or employee approve a purchase requisition, journal voucher, payment disbursement, or credit adjustment that they originated or posted. The maker (`posted_by`) and checker (`approved_by`) must be distinct individuals holding appropriate delegated financial authority. Any journal entry where `posted_by == approved_by` is strictly invalid and flagged as an acute internal control breach.

- **Clause 3.2: Prohibition of Shared Banking Credentials**  
  No commercial vendor, service contractor, or logistics partner payment shall be remitted to a bank account matching or associated with any active or former employee of Sahyadri Precision Components Pvt. Ltd. Enterprise Resource Planning (ERP) automated controls must continuously cross-check vendor disbursement accounts against employee payroll bank accounts.

- **Clause 3.3: Conflict of Interest Disclosure**  
  Any employee possessing direct or indirect familial, commercial, or equity interests in any prospective supplier must formally declare such conflict of interest prior to vendor onboarding. Such individuals are strictly barred from participating in vendor evaluation, quotation negotiation, or invoice authorization.

---

### Section 4: Anti-Structuring and Split-Payment Controls
- **Clause 4.1: Anti-Structuring Principle**  
  The deliberate division, fragmentation, or batching of purchase orders, invoices, or payment requests into multiple smaller disbursements to evade higher-tier delegated authority limits is strictly prohibited.

- **Clause 4.2: Structured Transaction Detection Window**  
  Multiple payments issued to the same commercial vendor within a rolling 48-hour window where individual amounts range between INR 46,000 and INR 49,800 (designed to circumvent the Tier 1 threshold of INR 50,000) shall automatically be flagged by automated audit algorithms as structured evasion of internal financial controls.

- **Clause 4.3: Corrective Actions and Disciplinary Sanctions**  
  Transactions identified as structured payments shall be frozen immediately. The initiating and approving officers shall be referred to the Executive Ethics Committee for formal inquiry and financial recovery.

---

### Section 5: Vendor Due Diligence, Banking Controls, and Operational Timing
- **Clause 5.1: Mandatory GSTIN and Onboarding Verification**  
  Prior to master data activation in the ERP system, all commercial suppliers must provide a valid 15-character Goods and Services Tax Identification Number (GSTIN) matching their Permanent Account Number (PAN) authenticated via the Government GST Portal. No payment shall be disbursed to entities with missing, malformed, or unverified GSTIN credentials. Furthermore, a mandatory minimum cooling-off period of 5 calendar days must elapse between vendor creation and the first financial payout.

- **Clause 5.2: Prohibition of Weekend Manual Postings**  
  Manual journal entries, invoice certifications, and vendor payments are prohibited on Saturdays and Sundays. The ERP system shall reject manual transaction posting during weekends, except for automated batch processes (e.g., scheduled depreciation, system interest accruals) certified in writing by the IT Systems Administrator.

- **Clause 5.3: Round-Amount Transaction Scrutiny**  
  Disbursements in exact round multiples of INR 10,000 (e.g., INR 50,000, INR 80,000, INR 1,00,000), particularly those posted outside standard working hours or on weekends, represent non-standard accounting practices and mandate immediate physical verification of original tax invoices, delivery challans, and Goods Receipt Notes (GRN).
