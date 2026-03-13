"use client";
// components/chat/VoiceButton.tsx

import { Mic, MicOff, Loader2 } from "lucide-react";
import { useVoice } from "@/hooks/useVoice";
import { clsx } from "clsx";

interface Props {
  onAudioReady: (blob: Blob) => void;
  onReady?: (reset: () => void) => void;
  disabled: boolean;
}

export default function VoiceButton({ onAudioReady, onReady, disabled }: Props) {
  const { state, error, startRecording, stopRecording, reset } = useVoice((blob) => {
    onAudioReady(blob);
  });

  // Expose reset function to parent via onReady callback
  // This allows the parent to reset voice state after processing completes
  if (onReady) {
    onReady(reset);
  }

  const isRecording = state === "recording";
  const isProcessing = state === "processing";

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        type="button"
        disabled={disabled || isProcessing}
        onClick={isRecording ? stopRecording : startRecording}
        className={clsx(
          "relative w-11 h-11 rounded-full flex items-center justify-center transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2 focus:ring-offset-surface-1",
          isRecording
            ? "bg-red-500 hover:bg-red-600 shadow-lg shadow-red-500/40"
            : "bg-surface-3 hover:bg-brand-600 text-ink-secondary hover:text-white",
          (disabled || isProcessing) && "opacity-40 cursor-not-allowed"
        )}
        title={isRecording ? "Stop recording" : "Start voice order"}
      >
        {/* Pulse ring while recording */}
        {isRecording && (
          <span className="absolute inset-0 rounded-full bg-red-500 animate-ping opacity-40" />
        )}
        {isProcessing
          ? <Loader2 size={18} className="animate-spin text-brand-400" />
          : isRecording
            ? <MicOff size={18} className="text-white" />
            : <Mic size={18} />
        }
      </button>
      {error && (
        <p className="text-xs text-red-400 max-w-[30] text-center">{error}</p>
      )}
    </div>
  );
}
