import { useRef } from 'react';

export function useAudioRecorder(onChunk: (pcm: ArrayBuffer) => void) {
  const contextRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const start = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }
    });
    streamRef.current = stream;

    const context = new AudioContext();
    contextRef.current = context;
    await context.resume();

    const workletCode = `
      class PCMProcessor extends AudioWorkletProcessor {
        constructor() {
          super();
          this.buffer = [];
          this.bufferSize = 4096;
        }
        downsample(input, inputRate, outputRate) {
          if (inputRate === outputRate) return input;
          const ratio = inputRate / outputRate;
          const outputLength = Math.floor(input.length / ratio);
          const output = new Float32Array(outputLength);
          for (let i = 0; i < outputLength; i++) {
            const start = Math.floor(i * ratio);
            const end = Math.floor((i + 1) * ratio);
            let sum = 0;
            for (let j = start; j < end && j < input.length; j++) sum += input[j];
            output[i] = sum / (end - start);
          }
          return output;
        }
        process(inputs) {
          const input = inputs[0][0];
          if (!input) return true;
          const downsampled = this.downsample(input, sampleRate, 16000);
          for (let i = 0; i < downsampled.length; i++) this.buffer.push(downsampled[i]);
          if (this.buffer.length >= this.bufferSize) {
            const chunk = new Float32Array(this.buffer.splice(0, this.bufferSize));
            const pcm = new Int16Array(chunk.length);
            for (let i = 0; i < chunk.length; i++) {
              pcm[i] = Math.max(-32768, Math.min(32767, chunk[i] * 32768));
            }
            this.port.postMessage(pcm.buffer, [pcm.buffer]);
          }
          return true;
        }
      }
      registerProcessor('pcm-processor', PCMProcessor);
    `;

    const blob = new Blob([workletCode], { type: 'application/javascript' });
    const url = URL.createObjectURL(blob);
    await context.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);

    const source = context.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(context, 'pcm-processor');
    workletRef.current = worklet;
    worklet.port.onmessage = (e) => onChunk(e.data);

    // Silent gain keeps the worklet in the active audio graph without playback
    const silentGain = context.createGain();
    silentGain.gain.value = 0;
    source.connect(worklet);
    worklet.connect(silentGain);
    silentGain.connect(context.destination);
  };

  const stop = () => {
    workletRef.current?.port.close();
    workletRef.current?.disconnect();
    workletRef.current = null;
    contextRef.current?.close();
    contextRef.current = null;
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  };

  return { start, stop };
}
