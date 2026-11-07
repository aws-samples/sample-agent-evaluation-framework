# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Provider implementations for judge clients.

This module contains concrete implementations of JudgeClient for
various LLM providers (Amazon Bedrock, OpenAI, Anthropic, etc.).
"""

from agent_eval.providers.bedrock_client import BedrockJudgeClient

__all__ = ['BedrockJudgeClient']
