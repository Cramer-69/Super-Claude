"""Optional third-party integrations (plugins) for the conductor.

Every module here follows the same contract: the integration is inert
unless its package is installed *and* its credentials are configured, and
no call it makes may raise into a chat request.
"""
