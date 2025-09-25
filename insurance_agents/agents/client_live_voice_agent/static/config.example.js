// Configuration file for Azure AI Services and Database connections
// This is an EXAMPLE file - copy this to config.js and replace with your actual values
// The actual config.js file should NOT be committed to version control
// Make sure config.js is in .gitignore

window.AZURE_CONFIG = {
    // Azure Voice Live API Configuration
    endpoint: "https://your-voice-resource.cognitiveservices.azure.com/",
    apiKey: "YOUR_AZURE_VOICE_API_KEY_HERE",
    model: "gpt-4o-realtime-preview",
    voice: "en-US-JennyMultilingualNeural"
};

window.COSMOS_CONFIG = {
    // Cosmos DB Configuration for Claims Data
    endpoint: "https://your-cosmos-account.documents.azure.com:443/",
    key: "YOUR_COSMOS_DB_PRIMARY_KEY_HERE",
    database: "insurance",
    container: "claim_details"
};

// Legacy naming for compatibility
window.VOICE_CONFIG = window.AZURE_CONFIG;

console.log('✅ Config loaded - Azure endpoint:', window.AZURE_CONFIG.endpoint);
console.log('✅ Config loaded - Model:', window.AZURE_CONFIG.model);
console.log('✅ Config loaded - Voice:', window.AZURE_CONFIG.voice);