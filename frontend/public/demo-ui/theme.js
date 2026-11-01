/* Demo preferences are separate from the production application's theme. */
try {
  const saved = localStorage.getItem('hx-demo-theme');
  document.documentElement.dataset.theme = saved === 'dark' || (saved !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
} catch { /* The HTML's default theme remains usable. */ }
