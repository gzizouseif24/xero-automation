# User Stories for Xero Payroll Automation

Add these user stories to the project plan; we'll verify them during development and testing.

- **User Story 1: Core Functionality** DONE
  - As a payroll administrator, I want to run the tool by uploading a folder containing the relevant files, so that a complete draft pay run is created in Xero without manual data entry.

- **User Story 2: Data Accuracy**   DONE
  - As a payroll administrator, I want to check any draft payslip, so that I can see all hours (regular, overtime, travel, holiday) are correctly recorded and calculated.

  -----------------------------------------------------------

- **User Story 3: Region Costing**  
  - As a Management Accountant, I want to run a "P&L by Tracking Category" report, so that I can see accurate, real-time labor costs per region without a manual journal.

  - London region: $5,000 labor costs this month
   Manchester region: $3,200 labor costs this month
    etc.

    No manual work needed - real-time regional cost tracking!

- **User Story 4: Robust Error Handling (Regions)**
  - As a payroll administrator, I want the tool to stop and clearly report which region name from the source file isn't listed in Xero, so that I know exactly which region to add in the Xero UI before I re-run the tool.

- **User Story 5: Interactive Employee Matching**
  - As a payroll administrator, I want the tool to handle ambiguous employee names by:
    1. Suggesting the most likely match from Xero (e.g., matching "P. Kelly" to "Patrick Kelly") and letting me confirm or reject it.
    2. If I reject the suggestion, or if no likely match is found, stopping the process and clearly reporting the unresolved name.
  - So that I can efficiently process clear matches and am given a precise instruction to add or correct the employee's details in Xero before re-running the tool.


