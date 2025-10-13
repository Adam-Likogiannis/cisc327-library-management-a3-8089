"""
Main Flask application entry point for the Library Management System.

This module provides the application factory pattern for creating Flask app instances.
Routes are organized in separate blueprint modules in the routes package.
"""

from flask import Flask
from database import init_database, add_sample_data
from routes import register_blueprints


def create_app():
    """
    Application factory function to create and configure Flask app.
    
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__)
    app.secret_key = "super secret key"
    
    # Initialize the database
    init_database()
    
    # Add sample data for testing and demonstration
    add_sample_data()
    
    # Register all route blueprints
    register_blueprints(app)
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
