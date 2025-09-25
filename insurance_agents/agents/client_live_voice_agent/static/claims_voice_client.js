class ClaimsVoiceLiveClient {
    constructor() {
        this.ws = null;
        this.audioContext = null;
        this.mediaStream = null;
        this.audioWorkletNode = null;
        this.isConnected = false;
        this.isRecording = false;
        

        
        // Audio settings
        this.sampleRate = 24000;
        this.audioQueue = [];
        this.isPlaying = false;
        this.audioBufferQueue = [];
        this.nextPlayTime = 0;
        this.currentAudioSource = null;
        this.audioChunks = [];  // Buffer for accumulating audio chunks
        this.isProcessingAudio = false;
        
        // UI elements
        this.statusIndicator = document.getElementById('statusIndicator');
        this.statusText = document.getElementById('statusText');
        this.chatArea = document.getElementById('chatArea');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.startBtn = document.getElementById('startBtn');
        this.stopBtn = document.getElementById('stopBtn');
        
         // Configuration - Use config.js values if available, otherwise defaults
        console.log('🔍 Checking for config.js variables...', window.AZURE_CONFIG);
        
        this.endpointValue = (window.AZURE_CONFIG?.endpoint) || "";
        this.apiKeyValue = (window.AZURE_CONFIG?.apiKey) || "";
        this.modelValue = (window.AZURE_CONFIG?.model) || "gpt-4o-realtime-preview";
        this.voiceValue = (window.AZURE_CONFIG?.voice) || "en-US-JennyMultilingualNeural";
        
        // Validate that API key is available
        if (!this.apiKeyValue) {
            console.error('❌ No API key found in config.js');
            console.log('Available config:', window.AZURE_CONFIG);
        } else {
            console.log('✅ API key loaded from config.js');
        }
        
        
        // Transcript tracking
        this.currentResponse = '';
        this.responseTranscripts = new Map();
        this.completedResponses = new Set();
        this.activeResponseId = null;           // Track current AI response
        this.cancelledResponses = new Set();     // Track cancelled responses
        this.isCancelling = false;               // Flag while cancellation in-flight
        this.scheduledSources = [];              // Track all scheduled buffer sources for interruption
        this.lastBargeInTime = 0;                // Timestamp of last interruption trigger
        this.bargeInCooldownMs = 1200;           // Minimum gap between interruption triggers
        this.pendingUserTranscript = '';          // Accumulate partial user transcript
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.startBtn.addEventListener('click', () => this.startChat());
        this.stopBtn.addEventListener('click', () => this.stopChat());
        
        // Enter key to start/stop
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !this.isConnected) {
                this.startChat();
            } else if (e.key === 'Escape' && this.isConnected) {
                this.stopChat();
            }
        });
    }

    updateStatus(status, text) {
        this.statusIndicator.className = `status-indicator ${status}`;
        this.statusText.textContent = text;
    }

    addMessage(sender, message, type = 'normal') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        if (type !== 'system') {
            const senderDiv = document.createElement('div');
            senderDiv.className = 'sender';
            senderDiv.textContent = sender;
            messageDiv.appendChild(senderDiv);
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.textContent = message;
        messageDiv.appendChild(contentDiv);
        
        this.chatArea.appendChild(messageDiv);
        this.chatArea.scrollTop = this.chatArea.scrollHeight;
    }

    showTyping(show) {
        this.typingIndicator.style.display = show ? 'flex' : 'none';
        if (show) {
            this.chatArea.scrollTop = this.chatArea.scrollHeight;
        }
    }

    async startChat() {
        try {
            this.updateStatus('connecting', 'Connecting...');
            this.startBtn.disabled = true;
            
            // Validate inputs
            if (!this.endpointValue || !this.apiKeyValue) {
                throw new Error('Please provide endpoint and API key');
            }
            
            // ADDED: Initialize backend systems (direct Cosmos DB + MCP fallback) before starting chat
            try {
                this.addMessage('System', '🔧 Initializing database systems...', 'system');
                const initResponse = await fetch('/api/startup/initialize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const initResult = await initResponse.json();
                
                if (initResult.ready) {
                    if (initResult.primary_method === 'direct_cosmos') {
                        this.addMessage('System', '✅ Database ready - direct Cosmos DB (primary) + MCP (fallback)', 'system');
                    } else if (initResult.primary_method === 'mcp_only') {
                        this.addMessage('System', '✅ Database ready - MCP access (direct Cosmos unavailable)', 'system');
                    } else {
                        this.addMessage('System', '⚠️ Voice agent ready, database will warm up during conversation', 'system');
                    }
                } else {
                    this.addMessage('System', '⚠️ Voice agent ready, database systems will initialize on first query', 'system');
                }
            } catch (initError) {
                console.warn('Backend initialization warning:', initError);
                this.addMessage('System', '⚠️ Backend systems will initialize during conversation', 'system');
            }
            
            // Initialize audio context
            await this.initializeAudio();
            
            // Connect to WebSocket
            await this.connectWebSocket();
            
            // Send session configuration for claims
            this.sendSessionUpdate();
            
            this.updateStatus('connected', 'Connected - Listening...');
            this.stopBtn.disabled = false;
            this.isConnected = true;
            
            this.addMessage('System', '🏥 Claims Assistant started! Ask about claim OP-02, IP-03, or any insurance terms.', 'system');
            
        } catch (error) {
            this.addMessage('System', `Error: ${error.message}`, 'system');
            this.updateStatus('disconnected', 'Connection failed');
            this.startBtn.disabled = false;
            console.error('Error starting chat:', error);
        }
    }

    async initializeAudio() {
        // Request microphone access
        this.mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: this.sampleRate,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        // Create audio context
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: this.sampleRate
        });

        // Create audio worklet for processing
        await this.audioContext.audioWorklet.addModule('audio-processor.js');
        
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.audioWorkletNode = new AudioWorkletNode(this.audioContext, 'audio-processor');
        
        // Handle audio data
        this.audioWorkletNode.port.onmessage = (event) => {
            if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
                const audioData = event.data;
                const base64Audio = this.arrayBufferToBase64(audioData);
                
                this.ws.send(JSON.stringify({
                    type: 'input_audio_buffer.append',
                    audio: base64Audio,
                    event_id: ''
                }));
            }
        };
        
        source.connect(this.audioWorkletNode);
    }

    connectWebSocket() {
        return new Promise((resolve, reject) => {
            const wsUrl = this.buildWebSocketUrl();
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected for Claims Assistant');
                resolve();
            };
            
            this.ws.onmessage = (event) => {
                this.handleWebSocketMessage(event.data);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(new Error('WebSocket connection failed'));
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.handleDisconnection();
            };
        });
    }

    buildWebSocketUrl() {
        const endpoint = this.endpointValue.replace('https://', 'wss://').replace(/\/$/, '');
        const apiVersion = '2025-05-01-preview';
        const model = this.modelValue;
        const apiKey = this.apiKeyValue;
        
        console.log('🔗 Connecting with model:', model);
        return `${endpoint}/voice-live/realtime?api-version=${apiVersion}&model=${model}&api-key=${apiKey}`;
    }

    sendSessionUpdate() {
        const chosenModel = this.modelValue;
        const isRealtime = /realtime/i.test(chosenModel) || /mm-realtime/i.test(chosenModel);
        console.log('Configuring Claims Assistant session:', { chosenModel, isRealtime });
        
        // For realtime models, use a simpler transcription approach
        const transcriptionModel = isRealtime ? 'whisper-1' : 'gpt-4o-mini-transcribe';
        
        const sessionUpdate = {
            type: 'session.update',
            session: {
                instructions: `You are a helpful insurance claims assistant. You ONLY answer questions related to insurance claims in the claims database.

Your role is to:
1. Help customers check claim status, amounts, and details
2. Explain insurance terms and policy coverage
3. Assist with claim document requirements  
4. Provide information about claims processing

Important guidelines:
- ONLY discuss insurance claims from the claims database
- Be conversational and helpful
- Use the available tools to look up claim information
- If asked about topics outside of insurance claims, politely redirect to claims-related topics
- Keep responses concise but informative
- Ask for claim IDs when specific claim information is needed

Available sample claims:
- OP-02: Daniel Ong, $92 outpatient consultation, Status: Approved, Adjuster: Sarah Chen
- IP-03: John Doe, $928 inpatient care, Status: Under Review

Remember: You are here to help with insurance claims only. Be natural and conversational while staying focused on claims topics.`,
                modalities: ['audio','text'], // ensure both audio + text modalities
                turn_detection: (() => {
                    // Use slightly more sensitive params for realtime models for quicker barge-in and transcripts
                    const td = isRealtime ? {
                        type: 'azure_semantic_vad',
                        threshold: 0.4,
                        prefix_padding_ms: 300,
                        silence_duration_ms: 300,
                        remove_filler_words: true
                    } : {
                        type: 'azure_semantic_vad',
                        threshold: 0.4,
                        prefix_padding_ms: 300,
                        silence_duration_ms: 300,
                        remove_filler_words: true,
                        end_of_utterance_detection: {
                            model: 'semantic_detection_v1',
                            threshold: 0.006,
                            timeout: 1.2
                        }
                    };
                    return td;
                })(),
                input_audio_noise_reduction: {
                    type: 'azure_deep_noise_suppression'
                },
                input_audio_echo_cancellation: {
                    type: 'server_echo_cancellation'
                },
                voice: {
                    name: this.voiceValue,
                    type: 'azure-standard'
                },
                // Always request transcription explicitly so user text shows even for realtime models
                input_audio_transcription: {
                    enabled: true,
                    model: transcriptionModel,
                    format: 'text'
                },
                tools: [
                    {
                        type: "function",
                        name: "getClaim",
                        description: "Get claim details from the insurance database",
                        parameters: {
                            type: "object",
                            properties: {
                                claim_id: {
                                    type: "string",
                                    description: "The claim ID to look up (e.g., OP-02, IP-03)"
                                }
                            },
                            required: ["claim_id"]
                        }
                    },
                    {
                        type: "function",
                        name: "getDefinition", 
                        description: "Get definition of insurance terms and policy details",
                        parameters: {
                            type: "object",
                            properties: {
                                term: {
                                    type: "string",
                                    description: "The insurance term to define (e.g., deductible, copay, premium)"
                                }
                            },
                            required: ["term"]
                        }
                    },
                    {
                        type: "function",
                        name: "prepareUploadLink",
                        description: "Generate secure upload link for claim documents",
                        parameters: {
                            type: "object",
                            properties: {
                                claim_id: {
                                    type: "string",
                                    description: "The claim ID"
                                },
                                document_type: {
                                    type: "string", 
                                    description: "Type of document to upload (medical_report, receipt, prescription, etc.)"
                                }
                            },
                            required: ["claim_id", "document_type"]
                        }
                    }
                ]
            },
            event_id: ''
        };
        
        this.ws.send(JSON.stringify(sessionUpdate));
    }

    handleWebSocketMessage(data) {
        try {
            const event = JSON.parse(data);
            const eventType = event.type;
            
            console.log('Received event:', eventType);
            
            switch (eventType) {
                case 'session.created':
                    console.log('Claims Assistant session created');
                    // Start the conversation by creating a response
                    this.ws.send(JSON.stringify({
                        type: 'response.create',
                        response: {
                            modalities: ['text', 'audio'],
                            instructions: 'Welcome the user to the Claims Assistant. Ask how you can help with their insurance claims today.'
                        }
                    }));
                    break;
                    
                case 'input_audio_buffer.speech_started':
                    const nowTs = Date.now();
                    // Debounce multiple rapid speech_started events
                    if (nowTs - this.lastBargeInTime < this.bargeInCooldownMs) {
                        console.log('🛑 Ignoring speech_started (within cooldown)');
                        break;
                    }
                    // Only treat as interruption if AI audio is currently playing / scheduled or active response present
                    const aiSpeaking = this.scheduledSources.length > 0 || this.currentAudioSource;
                    if (aiSpeaking || (this.activeResponseId && !this.isCancelling)) {
                        this.addMessage('System', '🎤 Speech detected (interrupt)...', 'system');
                        this.interruptForUserSpeech();
                        this.lastBargeInTime = nowTs;
                    } else {
                        console.log('Speech started (no AI audio to interrupt)');
                    }
                    break;
                    
                case 'input_audio_buffer.speech_stopped':
                    console.log('Speech stopped event received');
                    break;
                    
                case 'response.created':
                    this.showTyping(true);
                    this.currentResponse = '';
                    // Allow currently scheduled audio to finish; only reset chunk accumulator
                    this.audioChunks = [];
                    // Maintain nextPlayTime so new audio appends seamlessly
                    this.isCancelling = false;
                    this.activeResponseId = (event.response && event.response.id) || event.response_id || event.item_id || null;
                    // Clear any leftover cancelled response audio
                    this.stopAllScheduledAudio();
                    break;
                    
                case 'conversation.item.created':
                    // Handle user transcript from conversation item
                    try {
                        const item = event.item || event.data || {};
                        if (item.type === 'input_audio' && item.transcript) {
                            console.log('✅ User transcript (item.created):', item.transcript);
                            this.addMessage('👤 You', item.transcript, 'user');
                        }
                        // Sometimes transcript nested in content array
                        if (item.type === 'input_audio' && Array.isArray(item.content)) {
                            for (const c of item.content) {
                                if (c.transcript) {
                                    console.log('✅ User transcript (item.content):', c.transcript);
                                    this.addMessage('👤 You', c.transcript, 'user');
                                    break;
                                }
                            }
                        }
                    } catch(e) {
                        console.warn('conversation.item.created parse issue', e);
                    }
                    break;
                    
                case 'conversation.item.input_audio_transcription.completed':
                    const userTranscript = event.transcript;
                    if (userTranscript) {
                        console.log('✅ User transcription completed:', userTranscript);
                        this.addMessage('👤 You', userTranscript, 'user');
                        this.pendingUserTranscript = '';
                    }
                    break;
                    
                case 'response.audio_transcript.delta':
                    const delta = event.delta;
                    const responseId = event.response_id || event.item_id;
                    
                    if (delta && responseId) {
                        if (!this.responseTranscripts.has(responseId)) {
                            this.responseTranscripts.set(responseId, '');
                        }
                        
                        const updatedTranscript = this.responseTranscripts.get(responseId) + delta;
                        this.responseTranscripts.set(responseId, updatedTranscript);
                        this.currentResponse = updatedTranscript;
                    }
                    break;
                    
                case 'response.audio_transcript.done':
                    const finalResponseId = event.response_id || event.item_id;
                    
                    if (finalResponseId && !this.completedResponses.has(finalResponseId)) {
                        this.completedResponses.add(finalResponseId);
                        if (this.activeResponseId === finalResponseId) {
                            this.activeResponseId = null; // Clear active if done
                        }
                        this.showTyping(false);
                        
                        const finalTranscript = this.responseTranscripts.get(finalResponseId) || this.currentResponse;
                        if (finalTranscript) {
                            this.addMessage('🏥 Claims Assistant', finalTranscript, 'assistant');
                        }
                    }
                    break;
                    
                case 'response.audio.delta':
                    const audioData = event.delta;
                    console.log('🔊 AUDIO DELTA EVENT RECEIVED');
                    if (this.isCancelling) {
                        console.log('⚠️ Ignoring audio delta during cancellation');
                        break;
                    }
                    if (audioData) {
                        // Buffer the audio chunk instead of playing immediately
                        this.audioChunks.push(audioData);
                        this.processAudioBuffer();
                    }
                    break;
                    
                case 'response.audio.done':
                    console.log('🔊 AUDIO DONE EVENT RECEIVED');
                    // Process any remaining audio and mark as complete
                    this.processAudioBuffer(true);
                    break;
                    
                case 'response.function_call_arguments.done':
                    // Handle tool calls - use real API calls to CosmosDB
                    const functionName = event.name;
                    const args = JSON.parse(event.arguments || '{}');
                    console.log('Function call:', functionName, args);
                    
                    this.handleFunctionCall(functionName, args, event.call_id);
                    break;
                    
                case 'error':
                    const error = event.error || {};
                    let msg = (error.message || error.code || 'Unknown error');
                    this.addMessage('System', `Error: ${msg}`, 'system');
                    console.error('Server error FULL EVENT:', event);
                    break;
            }
            
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }

    // Real API calls to CosmosDB (replaces simulated functions)
    async getClaim(claimId) {
        try {
            const response = await fetch(`/api/claims/${claimId}`);
            const data = await response.json();
            
            if (data.error) {
                return `Claim ${claimId} not found in our database. Error: ${data.error}`;
            }
            
            // Format the real claim data
            let result = `Claim ${data.claimId}:\n`;
            result += `Patient: ${data.patientName}\n`;
            result += `Category: ${data.category}\n`;
            result += `Amount: $${data.billAmount}\n`;
            result += `Status: ${data.status}\n`;
            result += `Bill Date: ${data.billDate}\n`;
            result += `Submitted: ${new Date(data.submittedAt).toLocaleDateString()}\n`;
            result += `Assigned to: ${data.assignedEmployeeName} (${data.assignedEmployeeID})\n`;
            result += `Member ID: ${data.memberId}\n`;
            result += `Region: ${data.region}\n`;
            result += `Diagnosis: ${data.diagnosis}\n`;
            result += `Service Type: ${data.serviceType}\n`;
            
            if (data.lastUpdatedAt) {
                result += `Last Updated: ${new Date(data.lastUpdatedAt).toLocaleDateString()}\n`;
            }
            
            // Add attachment information if available
            if (data.billAttachment || data.memoAttachment || data.dischargeAttachment) {
                result += `\nDocuments available:\n`;
                if (data.billAttachment) result += `• Medical Bill\n`;
                if (data.memoAttachment) result += `• Memo\n`;
                if (data.dischargeAttachment) result += `• Discharge Summary\n`;
            }
            
            return result;
        } catch (error) {
            console.error('Error fetching claim:', error);
            return `Sorry, I cannot access the claims database right now. CosmosDB might be unreachable. Please try again later.`;
        }
    }

    async searchClaims(searchTerm) {
        try {
            const response = await fetch(`/api/claims/search?q=${encodeURIComponent(searchTerm)}`);
            const data = await response.json();
            
            if (data.error) {
                return `Error searching claims: ${data.error}`;
            }
            
            if (data.count === 0) {
                return `No claims found matching "${searchTerm}". Try searching by claim ID, patient name, or diagnosis.`;
            }
            
            let result = `Found ${data.count} claim(s) matching "${searchTerm}":\n\n`;
            
            data.claims.slice(0, 5).forEach(claim => {  // Limit to 5 results for voice response
                result += `• ${claim.claimId}: ${claim.patientName} - $${claim.billAmount} (${claim.status})\n`;
            });
            
            if (data.count > 5) {
                result += `\n... and ${data.count - 5} more results. Ask for a specific claim ID for details.`;
            }
            
            return result;
        } catch (error) {
            console.error('Error searching claims:', error);
            return `Sorry, I cannot search the claims database right now. CosmosDB might be unreachable. Please try again later.`;
        }
    }

    async handleFunctionCall(functionName, args, callId) {
        try {
            let result = '';
            
            if (functionName === 'getClaim') {
                result = await this.getClaim(args.claim_id);
            } else if (functionName === 'getDefinition') {
                result = this.simulateGetDefinition(args.term);
            } else if (functionName === 'prepareUploadLink') {
                result = this.simulatePrepareUploadLink(args.claim_id, args.document_type);
            } else {
                result = `Unknown function: ${functionName}`;
            }
            
            // Send function result back
            const functionResult = {
                type: 'conversation.item.create',
                item: {
                    type: 'function_call_output',
                    call_id: callId,
                    output: result
                }
            };
            this.ws.send(JSON.stringify(functionResult));
            
            // Trigger response generation
            this.ws.send(JSON.stringify({ type: 'response.create' }));
            
        } catch (error) {
            console.error('Error handling function call:', error);
            
            // Send error result back
            const errorResult = {
                type: 'conversation.item.create',
                item: {
                    type: 'function_call_output',
                    call_id: callId,
                    output: `Error: Unable to process request. ${error.message}`
                }
            };
            this.ws.send(JSON.stringify(errorResult));
            this.ws.send(JSON.stringify({ type: 'response.create' }));
        }
    }

    simulateGetDefinition(term) {
        const definitions = {
            "deductible": "The amount you must pay out-of-pocket before insurance coverage begins.",
            "copay": "A fixed amount you pay for a covered service, usually at the time of service.",
            "coinsurance": "Your share of costs after you've met your deductible, expressed as a percentage.",
            "premium": "The monthly amount you pay for your insurance coverage.",
            "out-of-pocket maximum": "The most you'll pay for covered services in a year.",
            "network": "Healthcare providers who have contracted with your insurance plan.",
            "prior authorization": "Approval required before certain services or medications are covered.",
            "claim": "A request for payment for medical services you've received.",
            "adjuster": "The insurance professional who reviews and processes your claim.",
            "consultation": "A medical appointment where you discuss your health with a healthcare provider.",
            "inpatient": "Medical care received while staying overnight in a hospital.",
            "outpatient": "Medical care received without staying overnight in a hospital."
        };
        
        const termLower = term.toLowerCase();
        for (const [key, definition] of Object.entries(definitions)) {
            if (key.includes(termLower) || termLower.includes(key)) {
                return `${key.charAt(0).toUpperCase() + key.slice(1)}: ${definition}`;
            }
        }
        
        return `Definition for '${term}' not found. I can help with common insurance terms like deductible, copay, coinsurance, premium, etc.`;
    }

    simulatePrepareUploadLink(claimId, documentType) {
        const uploadTypes = ["medical_report", "receipt", "prescription", "diagnosis", "treatment_plan", "other"];
        
        if (!uploadTypes.includes(documentType.toLowerCase())) {
            return `Invalid document type. Supported types: ${uploadTypes.join(', ')}`;
        }
        
        const uploadUrl = `https://claims-portal.insurance.com/upload/${claimId}/${documentType}?token=abc123xyz`;
        
        return `Upload link for ${documentType} on claim ${claimId}:\n${uploadUrl}\n\nThis link is valid for 24 hours. Please upload your ${documentType} document using this secure link.`;
    }

    processAudioBuffer(isComplete = false) {
        console.log('processAudioBuffer called:', {
            isProcessing: this.isProcessingAudio,
            chunks: this.audioChunks.length,
            isComplete
        });
        
        // Don't process if already processing
        if (this.isProcessingAudio) {
            console.log('Already processing audio, skipping');
            return;
        }

        // If we are cancelling, ignore any buffered audio until new response
        if (this.isCancelling) {
            console.log('Cancellation in progress - skipping buffer processing');
            return;
        }
        
        // Wait for more chunks unless complete or we have many chunks
        const minChunks = isComplete ? 1 : 5;
        if (this.audioChunks.length < minChunks) {
            console.log('Waiting for more chunks, current:', this.audioChunks.length, 'min:', minChunks);
            return;
        }
        
        // Process all accumulated chunks at once for better continuity
        const chunksToProcess = this.audioChunks.splice(0, this.audioChunks.length);
        console.log('Processing batch of', chunksToProcess.length, 'chunks');
        
        if (chunksToProcess.length > 0) {
            this.isProcessingAudio = true;
            this.playAudioChunks(chunksToProcess).then(() => {
                this.isProcessingAudio = false;
                console.log('Batch processed, remaining chunks:', this.audioChunks.length);
                // Process any remaining chunks
                if (this.audioChunks.length > 0) {
                    setTimeout(() => this.processAudioBuffer(false), 10);
                }
            }).catch(error => {
                console.error('Error processing audio batch:', error);
                this.isProcessingAudio = false;
            });
        }
    }

    async playAudioChunks(chunks) {
        try {
            console.log('playAudioChunks called with', chunks.length, 'chunks');
            
            // Combine multiple chunks into one buffer for smoother playback
            let totalLength = 0;
            const pcmDataArrays = [];
            
            // Decode all chunks
            for (const base64Audio of chunks) {
                try {
                    const binaryString = atob(base64Audio);
                    const audioData = new ArrayBuffer(binaryString.length);
                    const audioView = new Uint8Array(audioData);
                    
                    for (let i = 0; i < binaryString.length; i++) {
                        audioView[i] = binaryString.charCodeAt(i);
                    }
                    
                    const pcmData = new Int16Array(audioData);
                    pcmDataArrays.push(pcmData);
                    totalLength += pcmData.length;
                } catch (decodeError) {
                    console.error('Error decoding audio chunk:', decodeError);
                }
            }
            
            if (totalLength === 0) {
                console.log('No valid audio data to play');
                return;
            }
            
            console.log('Total PCM samples:', totalLength);
            
            // Combine all PCM data
            const combinedPcmData = new Int16Array(totalLength);
            let offset = 0;
            for (const pcmData of pcmDataArrays) {
                combinedPcmData.set(pcmData, offset);
                offset += pcmData.length;
            }
            
            // Create audio buffer
            const frameCount = combinedPcmData.length;
            const audioBuffer = this.audioContext.createBuffer(1, frameCount, this.sampleRate);
            const outputData = audioBuffer.getChannelData(0);
            
            // Convert 16-bit PCM to float32
            for (let i = 0; i < frameCount; i++) {
                outputData[i] = combinedPcmData[i] / 32768.0;
            }
            
            console.log('Created audio buffer:', {
                duration: audioBuffer.duration,
                sampleRate: audioBuffer.sampleRate,
                length: audioBuffer.length
            });

            // Schedule playback
            this.scheduleAudioPlayback(audioBuffer);
            
        } catch (error) {
            console.error('Error processing audio chunks:', error);
        }
    }

    async scheduleAudioPlayback(audioBuffer) {
        console.log('scheduleAudioPlayback called');
        
        // Ensure audio context is running
        if (this.audioContext.state === 'suspended') {
            console.log('🔊 RESUMING SUSPENDED AUDIO CONTEXT');
            await this.audioContext.resume();
        }
        
        // Check if buffer has meaningful duration (at least 10ms)
        if (audioBuffer.duration < 0.01) {
            console.log('Audio buffer too short, skipping:', audioBuffer.duration);
            return;
        }
        
        const source = this.audioContext.createBufferSource();
        const gainNode = this.audioContext.createGain();
        
        source.buffer = audioBuffer;
        gainNode.gain.value = 1.2; // Slight boost (safe headroom)
        if (gainNode.gain.value > 2.0) gainNode.gain.value = 2.0; // clamp
        
        // Connect: source -> gain -> destination
        source.connect(gainNode);
        gainNode.connect(this.audioContext.destination);
        
        console.log('🔊 AUDIO SETUP:', {
            audioContextState: this.audioContext.state,
            sampleRate: this.audioContext.sampleRate,
            bufferDuration: audioBuffer.duration,
            bufferChannels: audioBuffer.numberOfChannels,
            volume: gainNode.gain.value
        });

        // Play immediately instead of scheduling in future
        const currentTime = this.audioContext.currentTime;
        const startTime = Math.max(currentTime, this.nextPlayTime);
        
        console.log('Scheduling audio playback:', {
            currentTime,
            startTime,
            nextPlayTime: this.nextPlayTime,
            duration: audioBuffer.duration
        });
        
        console.log('🔊 STARTING AUDIO PLAYBACK AT:', startTime);
        source.start(startTime);
        this.currentAudioSource = source;

        // Track scheduled source for potential interruption
        this.scheduledSources.push({ source, startTime, duration: audioBuffer.duration });
        
        // Update next play time for seamless playback
        this.nextPlayTime = startTime + audioBuffer.duration;
        
        // Auto-cleanup when finished
        source.onended = () => {
            console.log('Audio playback ended naturally');
            if (this.currentAudioSource === source) {
                this.currentAudioSource = null;
            }
            // Remove from scheduled list
            this.scheduledSources = this.scheduledSources.filter(s => s.source !== source);
        };
        
        // Add error handling
        source.onerror = (error) => {
            console.error('Audio playback error:', error);
        };
    }

    stopCurrentAudio() {
        if (this.currentAudioSource) {
            try {
                this.currentAudioSource.stop();
            } catch (e) {
                // Audio might already be stopped
            }
            this.currentAudioSource = null;
        }
    }

    stopChat() {
        this.isConnected = false;
        this.showTyping(false);
        
        // Stop and reset all audio
        this.stopCurrentAudio();
        this.nextPlayTime = 0;
        this.audioBufferQueue = [];
        this.audioChunks = [];
        this.isProcessingAudio = false;
        
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }
        
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        
        this.updateStatus('disconnected', 'Disconnected');
        this.startBtn.disabled = false;
        this.stopBtn.disabled = true;
        
        this.addMessage('System', 'Claims Assistant chat stopped.', 'system');
    }

    interruptForUserSpeech() {
        try {
            // Stop current playback immediately
            this.stopAllScheduledAudio();
            // Clear queued / in-flight audio
            this.audioChunks = [];
            this.isProcessingAudio = false;
            this.nextPlayTime = this.audioContext ? this.audioContext.currentTime : 0;
            // Cancel active response server-side
            if (this.ws && this.ws.readyState === WebSocket.OPEN && this.activeResponseId && !this.completedResponses.has(this.activeResponseId)) {
                console.log('⛔ Sending response.cancel for response', this.activeResponseId);
                const cancelMsg = {
                    type: 'response.cancel',
                    response_id: this.activeResponseId,
                    event_id: ''
                };
                this.ws.send(JSON.stringify(cancelMsg));
                this.cancelledResponses.add(this.activeResponseId);
                this.isCancelling = true;
            }
        } catch (e) {
            console.error('Error during interruption:', e);
        }
    }

    stopAllScheduledAudio() {
        const now = this.audioContext ? this.audioContext.currentTime : 0;
        console.log('🛑 Stopping all scheduled audio sources. Count:', this.scheduledSources.length, 'currentTime:', now);
        for (const entry of this.scheduledSources) {
            try {
                entry.source.stop();
            } catch (e) { /* already stopped */ }
        }
        this.scheduledSources = [];
        this.currentAudioSource = null;
    }

    handleDisconnection() {
        if (this.isConnected) {
            this.stopChat();
            this.addMessage('System', 'Connection lost. Please try again.', 'system');
        }
    }

    // Utility functions
    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

    base64ToArrayBuffer(base64) {
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes.buffer;
    }
}

// Initialize the client when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.claimsClient = new ClaimsVoiceLiveClient();
});