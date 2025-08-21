o# Xero Payroll Automation Frontend

## Overview

The Xero Payroll Automation frontend is a web-based application designed to streamline the payroll process by automating timesheet processing. The application consists of multiple steps, each represented by a separate content area that is displayed based on the user's progress through the workflow.

## Structure

### `index.html`

The main HTML file that includes the following components:

- **Header**: Displays the application logo, title, and subtitle.
- **Workflow Steps**: A series of steps (Connect, Upload, Validate, Consolidate, Submit) that guide the user through the process.
- **Step Content**: Content areas for each step, only one of which is visible at a time.
- **Results Area**: Displays loading and results content.
- **Settings Modal**: Allows users to configure application settings.

### CSS Files

- **`variables.css`**: Contains CSS variables for colors, fonts, and other reusable styles.
- **`base.css`**: Resets styles and sets base styles for the body, container, and utility classes.
- **`typography.css`**: Defines typography styles for headings, subtitles, and other text elements.
- **`layout.css`**: Sets the layout for the header, workflow steps, and step content.
- **`components.css`**: Styles for buttons, alerts, and other reusable components.
- **`alerts.css`**: Styles for alert messages.
- **`file-upload.css`**: Styles for the file upload component.
- **`modal.css`**: Styles for the settings modal.
- **`settings.css`**: Styles for the settings form and tabs.
- **`forms.css`**: Styles for form elements.
- **`tables.css`**: Styles for tables.
- **`progress.css`**: Styles for the progress bar.
- **`responsive.css`**: Media queries for responsive design on different screen sizes.

### JavaScript Files

- **`app.js`**: Handles the application logic, including authentication, file uploads, data validation, consolidation, and submission.

## Functionality

1. **Authentication**:
   - Users can connect to their Xero account via OAuth.
   - The application checks the authentication status and advances to the next step if connected.

2. **File Upload**:
   - Users can drag and drop or select Excel files for upload.
   - Uploaded files are displayed in a list, and users can remove files from the list.

3. **Data Validation**:
   - The application validates employee names and regions against Xero data.
   - Validation results are displayed, and users can proceed to the next step if the data is valid.

4. **Data Consolidation**:
   - The application consolidates timesheet data into a final JSON format.
   - Users can download the consolidated JSON data.

5. **Submission**:
   - Users can submit the timesheets to Xero.
   - A dry run option is available for testing purposes.

## Usage

1. **Start the Server**:
   - Run `api_serve.py` to start the backend server.

2. **Access the Frontend**:
   - Open `index.html` in a web browser.

3. **Follow the Workflow**:
   - Connect to Xero.
   - Upload timesheet files.
   - Validate the data.
   - Consolidate the data.
   - Submit the timesheets to Xero.

## Troubleshooting

- **Scrolling Issue**:
  - Ensure that the browser console does not have any errors.
  - Disable any browser extensions and test the application again.
  - Verify that the CSS files do not have conflicting styles that might prevent scrolling.
