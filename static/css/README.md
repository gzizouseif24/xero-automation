# 🧩 Modular CSS Architecture

This directory contains the modular CSS files for the Xero Payroll Automation application. The CSS has been broken down into logical, focused modules for better maintainability.

## 📁 File Structure

```
static/css/
├── variables.css      # CSS custom properties and theme variables
├── base.css          # Reset styles, body, container, utilities
├── typography.css    # Text styles, headings, logo
├── layout.css        # Layout components (header, workflow, grid)
├── components.css    # UI components (buttons, badges, progress)
├── alerts.css        # Alert and notification styles
├── file-upload.css   # File upload and drag-drop styles
├── modal.css         # Modal and overlay styles
├── settings.css      # Settings form and tab styles
├── forms.css         # Form inputs, validation, lists, dictionaries
├── tables.css        # Table components and mapping displays
├── progress.css      # Progress bars and loading spinners
└── responsive.css    # Media queries and responsive design
```

## 🎯 Module Responsibilities

### `variables.css`
- CSS custom properties for colors, spacing, shadows
- Light and dark theme definitions
- Centralized design tokens

### `base.css`
- CSS reset and normalization
- Body and container base styles
- Utility classes (`.hidden`, etc.)

### `typography.css`
- Heading styles (h1, h2, etc.)
- Text utilities (`.subtitle`)
- Logo styling and responsive behavior

### `layout.css`
- Header and navigation layout
- Workflow steps and progress indicators
- Grid systems and card layouts

### `components.css`
- Button styles and variants
- Status badges and indicators
- Theme toggle functionality

### `alerts.css`
- Alert boxes (success, error, warning, info)
- Notification styles
- Feedback components

### `file-upload.css`
- Drag and drop upload areas
- File list and item styles
- Upload interaction states

### `modal.css`
- Modal overlay and content
- Modal header, body, footer
- Modal animations and positioning

### `settings.css`
- Settings tab navigation
- Settings content sections
- Tab switching functionality

### `forms.css`
- Form inputs and validation
- List and dictionary editors
- Settings status messages
- Form group layouts

### `tables.css`
- Mapping table styles
- Table hover effects
- Validation result displays

### `progress.css`
- Progress bars and animations
- Loading spinners
- Progress fill transitions

### `responsive.css`
- Mobile-first responsive design
- Breakpoint-specific adjustments
- Touch-friendly interactions

## 🔧 Usage

The CSS files are loaded in a specific order in `index.html`:

1. **Variables** - Must be loaded first for custom properties
2. **Base** - Foundation styles
3. **Typography** - Text and logo styles
4. **Layout** - Structural components
5. **Components** - Interactive elements
6. **Feature modules** - Specific functionality (alerts, upload, modal, settings, forms, tables, progress)
7. **Responsive** - Media queries last for proper cascade

## 🎨 Theme System

The modular system supports light/dark themes through CSS custom properties:

```css
/* Light theme (default) */
:root {
    --xero-blue: #1976d2;
    --xero-surface: #ffffff;
    /* ... */
}

/* Dark theme */
[data-theme="dark"] {
    --xero-blue: #2196f3;
    --xero-surface: #1e2a3a;
    /* ... */
}
```

## 🚀 Benefits

✅ **Maintainable** - Each file has a single responsibility
✅ **Scalable** - Easy to add new modules or modify existing ones
✅ **Cacheable** - Browsers can cache individual modules
✅ **Debuggable** - Easy to locate and fix specific styles
✅ **Reusable** - Modules can be used in other projects
✅ **Team-friendly** - Multiple developers can work on different modules

## 📝 Development Guidelines

1. **Keep modules focused** - Each file should have a clear purpose
2. **Use CSS custom properties** - Leverage the variable system
3. **Follow naming conventions** - Use consistent class naming
4. **Document changes** - Update this README when adding modules
5. **Test responsiveness** - Ensure mobile compatibility

## 🔄 Migration from Monolithic CSS

The original `styles.css` has been completely replaced with this modular system. If you need to revert:

1. Remove the modular CSS links from `index.html`
2. Restore the single `<link rel="stylesheet" href="/static/styles.css">`
3. The original file is preserved as backup

This modular approach provides better organization without requiring a build system or framework!