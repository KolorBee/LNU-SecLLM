from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import io
from PIL import Image
import json
import os
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for detection state
detection_active = False
detection_results = []

class MineRiskDetector:
    def __init__(self):
        self.risk_types = {
            'crack': {'color': (0, 0, 255), 'severity': 'high'},
            'loose_rock': {'color': (0, 165, 255), 'severity': 'medium'},
            'gas_leak': {'color': (255, 0, 0), 'severity': 'critical'},
            'structural_damage': {'color': (0, 255, 255), 'severity': 'high'},
            'slope_instability': {'color': (255, 255, 0), 'severity': 'critical'},
            'water_accumulation': {'color': (255, 0, 255), 'severity': 'medium'}
        }
        
    def detect_risks(self, image):
        """Detect mine risks using computer vision techniques"""
        detections = []
        
        # Convert to OpenCV format
        if isinstance(image, str):
            # Base64 encoded image
            image_data = base64.b64decode(image.split(',')[1])
            image = Image.open(io.BytesIO(image_data))
            image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Convert to grayscale for analysis
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Edge detection for cracks
        edges = cv2.Canny(gray, 50, 150)
        crack_contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Detect cracks
        for contour in crack_contours:
            area = cv2.contourArea(contour)
            if area > 100:  # Filter small contours
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                
                # Cracks are typically long and thin
                if aspect_ratio > 3 or aspect_ratio < 0.3:
                    confidence = min(0.9, area / 1000)
                    detections.append({
                        'type': 'crack',
                        'confidence': confidence,
                        'bbox': [x, y, x + w, y + h],
                        'severity': 'high'
                    })
        
        # Detect loose rocks using contour analysis
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        rock_contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in rock_contours:
            area = cv2.contourArea(contour)
            if 200 < area < 2000:  # Rock-sized objects
                x, y, w, h = cv2.boundingRect(contour)
                confidence = min(0.8, area / 1500)
                detections.append({
                    'type': 'loose_rock',
                    'confidence': confidence,
                    'bbox': [x, y, x + w, y + h],
                    'severity': 'medium'
                })
        
        # Detect structural damage using template matching
        # This is a simplified approach - in production, you'd use trained models
        structural_damage = self.detect_structural_damage(image)
        if structural_damage:
            detections.append(structural_damage)
        
        # Simulate gas leak detection (would use specialized sensors in real implementation)
        if np.random.random() < 0.1:  # 10% chance of gas leak detection
            x = np.random.randint(0, image.shape[1] - 100)
            y = np.random.randint(0, image.shape[0] - 100)
            detections.append({
                'type': 'gas_leak',
                'confidence': 0.85 + np.random.random() * 0.1,
                'bbox': [x, y, x + 100, y + 100],
                'severity': 'critical'
            })
        
        return detections
    
    def detect_structural_damage(self, image):
        """Detect structural damage using edge detection and morphology"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Detect irregular patterns that might indicate structural damage
        edges = cv2.Canny(gray, 30, 100)
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 500:  # Significant structural damage
                x, y, w, h = cv2.boundingRect(contour)
                return {
                    'type': 'structural_damage',
                    'confidence': min(0.9, area / 2000),
                    'bbox': [x, y, x + w, y + h],
                    'severity': 'high'
                }
        
        return None
    
    def calculate_risk_level(self, detections):
        """Calculate overall risk level based on detections"""
        if not detections:
            return 'low'
        
        critical_count = sum(1 for d in detections if d['severity'] == 'critical')
        high_count = sum(1 for d in detections if d['severity'] == 'high')
        medium_count = sum(1 for d in detections if d['severity'] == 'medium')
        
        if critical_count > 0:
            return 'critical'
        elif high_count >= 2:
            return 'high'
        elif high_count > 0 or medium_count >= 3:
            return 'medium'
        else:
            return 'low'
    
    def annotate_image(self, image, detections):
        """Annotate image with detection results"""
        annotated = image.copy()
        
        for detection in detections:
            bbox = detection['bbox']
            x1, y1, x2, y2 = bbox
            
            # Get color and severity info
            risk_info = self.risk_types.get(detection['type'], {'color': (128, 128, 128), 'severity': 'low'})
            color = risk_info['color']
            
            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"{detection['type'].replace('_', ' ').title()}: {detection['confidence']:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(annotated, (x1, y1 - label_size[1] - 10), (x1 + label_size[0], y1), color, -1)
            cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        return annotated

# Initialize detector
detector = MineRiskDetector()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'detection_active': detection_active
    })

@app.route('/api/process_frame', methods=['POST'])
def process_frame():
    """Process a single frame for AI detection"""
    global detection_results
    
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({'error': 'No image data provided'}), 400
        
        # Decode base64 image
        image_data = base64.b64decode(data['image'].split(',')[1])
        image = Image.open(io.BytesIO(image_data))
        image_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Perform detection
        detections = detector.detect_risks(image_cv)
        risk_level = detector.calculate_risk_level(detections)
        
        # Annotate image
        annotated_image = detector.annotate_image(image_cv, detections)
        
        # Convert annotated image back to base64
        _, buffer = cv2.imencode('.jpg', annotated_image)
        annotated_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # Update global results
        detection_results = detections
        
        return jsonify({
            'detections': detections,
            'risk_level': risk_level,
            'annotated_image': f"data:image/jpeg;base64,{annotated_base64}",
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error processing frame: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/start_detection', methods=['POST'])
def start_detection():
    """Start continuous detection"""
    global detection_active
    detection_active = True
    logger.info("AI detection started")
    return jsonify({'status': 'detection_started'})

@app.route('/api/stop_detection', methods=['POST'])
def stop_detection():
    """Stop continuous detection"""
    global detection_active
    detection_active = False
    logger.info("AI detection stopped")
    return jsonify({'status': 'detection_stopped'})

@app.route('/api/detection_status', methods=['GET'])
def detection_status():
    """Get current detection status and results"""
    return jsonify({
        'active': detection_active,
        'results': detection_results,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/calibrate', methods=['POST'])
def calibrate():
    """Calibrate detection parameters"""
    data = request.get_json()
    # In a real implementation, you would adjust detection parameters
    logger.info(f"Calibration requested with parameters: {data}")
    return jsonify({'status': 'calibrated'})

@app.route('/api/emergency_stop', methods=['POST'])
def emergency_stop():
    """Emergency stop all detection and alert systems"""
    global detection_active
    detection_active = False
    logger.warning("EMERGENCY STOP ACTIVATED")
    return jsonify({
        'status': 'emergency_stop_activated',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    # Create backend directory if it doesn't exist
    os.makedirs('backend', exist_ok=True)
    
    print("🚀 Starting MineGuard AI Backend Server...")
    print("📡 Server will be available at: http://localhost:5000")
    print("🔍 AI Detection endpoints:")
    print("   - POST /api/process_frame - Process camera frame")
    print("   - GET  /api/health - Health check")
    print("   - POST /api/start_detection - Start detection")
    print("   - POST /api/stop_detection - Stop detection")
    print("   - GET  /api/detection_status - Get status")
    print("   - POST /api/calibrate - Calibrate system")
    print("   - POST /api/emergency_stop - Emergency stop")
    print("\n🎯 Ready for mine risk detection!")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
