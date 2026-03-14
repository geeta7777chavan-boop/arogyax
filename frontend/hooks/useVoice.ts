// hooks/useVoice.ts — browser voice recording via MediaRecorder API
"use client";
import { useState, useRef, useCallback } from "react";

export type VoiceState = "idle" | "recording" | "processing";

export function useVoice(onAudioReady: (blob: Blob) => void) {
  const [state,   setState]   = useState<VoiceState>("idle");
  const [error,   setError]   = useState<string | null>(null);
  const mediaRef  = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Always reset to idle — call this after voice order completes
  const reset = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setState("idle");
    setError(null);
    chunksRef.current = [];
    if (mediaRef.current && mediaRef.current.state === "recording") {
      mediaRef.current.stop();
    }
    mediaRef.current = null;
  }, []);

  const startRecording = useCallback(async () => {
    // Always reset before starting a new recording
    reset();
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

        // Safety net — force reset after 30s if nothing else resets it
        timeoutRef.current = setTimeout(() => {
          setState("idle");
        }, 30000);
      };

      recorder.start();
      mediaRef.current = recorder;
      setState("recording");
    } catch (err) {
      setError("Microphone access denied. Please allow microphone permissions.");
      setState("idle");
    }
  }, [onAudioReady, reset]);

  const stopRecording = useCallback(() => {
    if (mediaRef.current && mediaRef.current.state === "recording") {
      mediaRef.current.stop();
    }
  }, []);

  return { state, error, startRecording, stopRecording, reset };
}