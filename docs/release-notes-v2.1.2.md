# Handy 2 2.1.2

## Fixes and changes

- **No more Edge popups**: the window is now a native window of the program itself (pywebview, using the WebView2 runtime that comes with Windows 10 / 11) instead of an Edge / Chrome app window. There is no browser profile any more, so no first-run screens, sign-in offers, Wallet, Shopping or Sidebar. The old `webview` folder in the program's data folder is no longer used and can be deleted.
- If the native window cannot start, the page opens in your default browser.
