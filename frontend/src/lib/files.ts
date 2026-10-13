import { getToken } from "@/lib/api";

/**
 * Fetch a bearer-protected file and open (or download) it.
 *
 * Source-document endpoints require the session token, so a plain anchor href
 * would 401. Fetching as a blob and handing the browser an object URL keeps the
 * auth header attached while still opening the regulator's document inline.
 */
export function openWithToken(url: string, download = false, filename?: string) {
  const token = getToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  void fetch(url, { headers })
    .then((response) => {
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      return response.blob();
    })
    .then((blob) => {
      const href = URL.createObjectURL(blob);
      if (download) {
        const anchor = document.createElement("a");
        anchor.href = href;
        if (filename) anchor.download = filename;
        anchor.click();
      } else {
        window.open(href, "_blank", "noopener,noreferrer");
      }
      setTimeout(() => URL.revokeObjectURL(href), 60_000);
    });
}
