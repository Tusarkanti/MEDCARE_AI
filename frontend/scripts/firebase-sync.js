/**
 * Firebase Sync Module
 * Handles syncing patient data between localStorage and Firebase Firestore
 */

let db = null;
let firebaseInitialized = false;

async function initializeFirebase() {
  if (firebaseInitialized) return true;
  
  try {
    if (typeof firebase === 'undefined') {
      console.warn('Firebase SDK not loaded');
      return false;
    }
    
    if (!firebase.apps.length) {
      firebase.initializeApp(APP_CONFIG.firebase);
    }
    
    db = firebase.firestore();
    firebaseInitialized = true;
    console.log('✅ Firebase initialized successfully');
    return true;
  } catch (error) {
    console.error('❌ Firebase initialization failed:', error);
    return false;
  }
}

async function syncPatientToFirebase(patientId, patientData) {
  if (!await initializeFirebase()) {
    console.warn('Firebase not available, skipping sync');
    return false;
  }
  
  try {
    const docRef = db.collection('patients').doc(patientId);
    await docRef.set({
      ...patientData,
      syncedAt: firebase.firestore.FieldValue.serverTimestamp(),
      lastUpdated: new Date().toISOString()
    }, { merge: true });
    
    console.log(`✅ Patient ${patientId} synced to Firebase`);
    return true;
  } catch (error) {
    console.error(`❌ Failed to sync patient ${patientId}:`, error);
    return false;
  }
}

async function syncAllPatientsToFirebase() {
  if (!await initializeFirebase()) {
    return { success: false, synced: 0, failed: 0, message: 'Firebase not initialized' };
  }
  
  let synced = 0;
  let failed = 0;
  const patients = [];
  
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key.startsWith('medcare_patient_')) {
      try {
        const patientData = JSON.parse(localStorage.getItem(key));
        const patientId = key.replace('medcare_patient_', '');
        
        const vitalsHistoryStr = localStorage.getItem(`medcare_vitals_history_${patientId}`);
        const vitalsHistory = vitalsHistoryStr ? JSON.parse(vitalsHistoryStr) : [];
        
        const fullData = {
          id: patientId,
          ...patientData,
          vitalsHistory,
          syncedAt: new Date().toISOString()
        };
        
        patients.push({ id: patientId, data: fullData });
      } catch (e) {
        console.error('Error parsing patient data:', e);
        failed++;
      }
    }
  }
  
  const batch = db.batch();
  
  for (const patient of patients) {
    try {
      const docRef = db.collection('patients').doc(patient.id);
      batch.set(docRef, {
        ...patient.data,
        syncedAt: firebase.firestore.FieldValue.serverTimestamp()
      }, { merge: true });
      synced++;
    } catch (e) {
      console.error(`Failed to add patient ${patient.id} to batch:`, e);
      failed++;
    }
  }
  
  try {
    await batch.commit();
    console.log(`✅ Batch sync complete: ${synced} patients synced`);
    return { success: true, synced, failed, message: `Synced ${synced} patients to Firebase` };
  } catch (error) {
    console.error('❌ Batch sync failed:', error);
    return { success: false, synced: 0, failed: patients.length, message: error.message };
  }
}

async function loadPatientsFromFirebase() {
  if (!await initializeFirebase()) {
    return [];
  }
  
  try {
    const snapshot = await db.collection('patients').orderBy('syncedAt', 'desc').get();
    const patients = [];
    
    snapshot.forEach(doc => {
      patients.push({ id: doc.id, ...doc.data() });
    });
    
    console.log(`✅ Loaded ${patients.length} patients from Firebase`);
    return patients;
  } catch (error) {
    console.error('❌ Failed to load from Firebase:', error);
    return [];
  }
}

async function deletePatientFromFirebase(patientId) {
  if (!await initializeFirebase()) {
    return false;
  }
  
  try {
    await db.collection('patients').doc(patientId).delete();
    console.log(`✅ Patient ${patientId} deleted from Firebase`);
    return true;
  } catch (error) {
    console.error(`❌ Failed to delete patient ${patientId}:`, error);
    return false;
  }
}

async function saveIntakeToFirebase(intakeData) {
  if (!await initializeFirebase()) {
    return false;
  }
  
  const patientId = intakeData.mobile_number || intakeData.id || Date.now().toString();
  
  try {
    await db.collection('patients').doc(patientId).set({
      ...intakeData,
      createdAt: firebase.firestore.FieldValue.serverTimestamp(),
      syncedAt: firebase.firestore.FieldValue.serverTimestamp()
    }, { merge: true });
    
    console.log(`✅ Intake saved to Firebase for ${patientId}`);
    return true;
  } catch (error) {
    console.error('❌ Failed to save intake:', error);
    return false;
  }
}

window.syncPatientToFirebase = syncPatientToFirebase;
window.syncAllPatientsToFirebase = syncAllPatientsToFirebase;
window.loadPatientsFromFirebase = loadPatientsFromFirebase;
window.deletePatientFromFirebase = deletePatientFromFirebase;
window.saveIntakeToFirebase = saveIntakeToFirebase;
window.initializeFirebase = initializeFirebase;
