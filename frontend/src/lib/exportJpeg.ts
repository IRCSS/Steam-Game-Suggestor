import { toJpeg } from "html-to-image";

/** Render a DOM node (the off-screen ExportCard) to a JPEG data URL. */
export async function renderJpeg(node: HTMLElement): Promise<string> {
  return toJpeg(node, {
    quality: 0.92,
    pixelRatio: 2,
    backgroundColor: "#080c13",
    width: node.offsetWidth,
    height: node.offsetHeight,
  });
}

/** Resolve once `settled` is called, or after `ms` as a safety net (slow/offline artwork). */
export function waitFor(register: (done: () => void) => void, ms = 8000): Promise<void> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, ms);
    register(() => {
      window.clearTimeout(timer);
      resolve();
    });
  });
}
