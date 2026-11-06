import { useCallback, useEffect, useRef, useState } from "react";

export function useToast(durationMs = 2400) {
  const [message, setMessage] = useState("");
  const [visible, setVisible] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const show = useCallback(
    (text: string) => {
      setMessage(text);
      setVisible(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setVisible(false), durationMs);
    },
    [durationMs],
  );

  useEffect(() => () => window.clearTimeout(timer.current), []);
  return { message, visible, show };
}

export function Toast({ message, visible }: { message: string; visible: boolean }) {
  return (
    <div id="toast" className={`toast${visible ? " visible" : ""}`} role="status" aria-live="polite">
      {message}
    </div>
  );
}
