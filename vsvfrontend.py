"""
VSV Store - Launcher Script
============================
Simple launcher that imports and runs the main Flask application.
Run this file to start the VSV Store web application on port 5000.
"""

from app import app

if __name__ == '__main__':
    app.run(debug=True, port=5000)
