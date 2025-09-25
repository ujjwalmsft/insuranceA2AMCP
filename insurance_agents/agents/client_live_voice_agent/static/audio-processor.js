class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 1200; // 50ms at 24kHz
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        
        if (input.length > 0) {
            const inputChannel = input[0];
            
            for (let i = 0; i < inputChannel.length; i++) {
                this.buffer[this.bufferIndex] = inputChannel[i];
                this.bufferIndex++;
                
                if (this.bufferIndex >= this.bufferSize) {
                    // Convert float32 to int16
                    const int16Buffer = new Int16Array(this.bufferSize);
                    for (let j = 0; j < this.bufferSize; j++) {
                        // Clamp to [-1, 1] and convert to 16-bit
                        const sample = Math.max(-1, Math.min(1, this.buffer[j]));
                        int16Buffer[j] = Math.round(sample * 32767);
                    }
                    
                    // Send the audio data to the main thread
                    this.port.postMessage(int16Buffer.buffer);
                    
                    // Reset buffer
                    this.bufferIndex = 0;
                }
            }
        }
        
        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor);
