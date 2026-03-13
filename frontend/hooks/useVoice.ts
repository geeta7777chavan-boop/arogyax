// hooks/useVoice.ts — browser voice recording via MediaRecorder API

"use client";
import { useState, useRef, useCallback } from "react";

export type VoiceState = "idle" | "recording" | "processing";

export function useVoice(onAudioReady: (blob: Blob) => void) {
  const [state,    setState]    = useState<VoiceState>("idle");
  const [error,    setError]    = useState<string | null>(null);
  const mediaRef   = useRef<MediaRecorder | null>(null);
  const chunksRef  = useRef<BlobPart[]>([]);

  const startRecording = useCallback(async () => {
    setError(null);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        stream.getTracks().forEach(t => t.stop());
        setState("processing");
        onAudioReady(blob);
      };

      recorder.start();
      mediaRef.current = recorder;
      setState("recording");
    } catch (err) {
      setError("Microphone access denied. Please allow microphone permissions.");
      setState("idle");
    }
  }, [onAudioReady]);

  const stopRecording = useCallback(() => {
    if (mediaRef.current && mediaRef.current.state === "recording") {
      mediaRef.current.stop();
    }
  }, []);

  const reset = useCallback(() => setState("idle"), []);

  return { state, error, startRecording, stopRecording, reset };
}
