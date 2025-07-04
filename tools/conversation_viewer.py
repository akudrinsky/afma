#!/usr/bin/env python3
"""
Conversation Viewer - A simple web app to explore conversation data.
Run with: streamlit run conversation_viewer.py
"""

import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx
import matplotlib.pyplot as plt
import io
import base64
from collections import defaultdict, Counter
from typing import List, Dict, Any
import os
import sys
from pathlib import Path

from afma.alignment_visualization import (
    create_trace_alignment_graph_base64 as create_trace_alignment_graph,
    create_merged_trace_alignment_graph_base64,
    get_graph_statistics
)


@st.cache_data
def load_conversations(file_path: str) -> List[Dict[str, Any]]:
    """Load conversations from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def similarity_metric(seq1: List[str], seq2: List[str]) -> float:
    """Calculate normalized Levenshtein Distance similarity between two sequences.
    
    Returns a similarity score between 0 and 1, where:
    - 1.0 means sequences are identical
    - 0.0 means sequences are completely different
    """
    if not seq1 and not seq2:
        return 1.0
    if not seq1 or not seq2:
        return 0.0
    
    # Calculate Levenshtein distance using dynamic programming
    len1, len2 = len(seq1), len(seq2)
    
    # Create a matrix to store distances
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    # Initialize base cases
    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j
    
    # Fill the matrix
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            if seq1[i-1] == seq2[j-1]:
                dp[i][j] = dp[i-1][j-1]  # No operation needed
            else:
                dp[i][j] = 1 + min(
                    dp[i-1][j],    # Deletion
                    dp[i][j-1],    # Insertion
                    dp[i-1][j-1]   # Substitution
                )
    
    # Get the Levenshtein distance
    distance = dp[len1][len2]
    
    # Normalize to similarity score (0-1 range)
    max_len = max(len1, len2)
    similarity = 1.0 - (distance / max_len) if max_len > 0 else 1.0
    
    return similarity


def get_similarity_score(conv: Dict[str, Any], trace_alignments: Dict[str, Any] = None) -> tuple[float, str]:
    """Get similarity score from alignment data or calculate as fallback."""
    # First try to get from trace alignment data
    if trace_alignments and conv.get("trace_set_id"):
        trace_set_id = conv["trace_set_id"]
        instantiation_id = conv.get("instantiation_id", 0)
        
        if trace_set_id in trace_alignments:
            alignment_data = trace_alignments[trace_set_id]
            alignments = alignment_data.get("alignments", [])
            
            # Find the alignment for this specific instantiation
            if instantiation_id < len(alignments):
                alignment = alignments[instantiation_id]
                return alignment.get("similarity", 0.0), "Weighted Levenshtein"
    
    # Fallback to basic similarity calculation
    user_source_tools = [tool.get('name', '') for tool in conv.get('user_source', [])]
    used_tools = conv.get('used_tools', [])
    similarity = similarity_metric(user_source_tools, used_tools)
    return similarity, "Basic Levenshtein"


def get_goal_achievement_score(conv: Dict[str, Any], trace_alignments: Dict[str, Any] = None) -> float:
    """Get goal achievement score for a conversation from trace alignments if available."""
    trace_set_id = conv.get("trace_set_id")
    inst_id = conv.get("instantiation_id", 0)
    if trace_alignments and trace_set_id and trace_set_id in trace_alignments:
        goal_results = trace_alignments[trace_set_id].get("goal_achievement_results", [])
        for result in goal_results:
            if result.get("conversation_id", -1) == conv.get("conversation_id", -1) or result.get("conversation_id", -1) == conv.get("original_index", -1):
                return result.get("score", 0.0)
        # fallback: try by instantiation_id order
        if inst_id < len(goal_results):
            return goal_results[inst_id].get("score", 0.0)
    return 0.0


def get_goal_achievement_summary(trace_set: Dict[str, Any]) -> float:
    """Get avg goal achievement score for a trace set from alignment summary."""
    return trace_set.get("avg_goal_achievement", 0.0)


# ========== NEW GRAPH IMPLEMENTATION ==========

# All graph implementation functions are now imported from afma.alignment_visualization module

# ========== END NEW GRAPH IMPLEMENTATION ==========


def load_files_from_folder(folder_path: str) -> tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Load conversation files automatically from a folder by expected names."""
    conversations = []
    trace_alignments = {}
    alignment_summary = []
    
    folder = Path(folder_path)
    if not folder.exists():
        st.error(f"Folder does not exist: {folder_path}")
        return conversations, trace_alignments, alignment_summary
    
    # Expected file names
    conversation_files = ["conversations.json", "conversation_data.json", "conversations_data.json"]
    alignment_files = ["trace_alignments.json", "alignments.json"]
    summary_files = ["alignment_summary.json", "summary.json", "trace_summary.json"]
    
    # Load conversations
    for filename in conversation_files:
        filepath = folder / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    conversations = json.load(f)
                st.success(f"✅ Loaded {len(conversations)} conversations from {filename}")
                break
            except Exception as e:
                st.warning(f"⚠️ Error loading {filename}: {e}")
    else:
        st.warning(f"📁 No conversation file found in {folder_path}. Looking for: {', '.join(conversation_files)}")
    
    # Load trace alignments
    for filename in alignment_files:
        filepath = folder / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    trace_alignments = json.load(f)
                st.success(f"✅ Loaded alignments for {len(trace_alignments)} trace sets from {filename}")
                break
            except Exception as e:
                st.warning(f"⚠️ Error loading {filename}: {e}")
    
    # Load alignment summary
    for filename in summary_files:
        filepath = folder / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    alignment_summary = json.load(f)
                st.success(f"✅ Loaded alignment summary for {len(alignment_summary)} trace sets from {filename}")
                break
            except Exception as e:
                st.warning(f"⚠️ Error loading {filename}: {e}")
    
    return conversations, trace_alignments, alignment_summary


def analyze_alignment_patterns(trace_alignments: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze common error patterns from all trace alignments."""
    if not trace_alignments:
        return {}
    
    # Counters for different types of operations
    substitutions = Counter()  # (from_tool, to_tool) pairs
    insertions = Counter()     # inserted tools
    deletions = Counter()      # deleted tools
    total_operations = Counter()  # operation types
    
    # Process all trace alignments
    for trace_set_id, alignment_data in trace_alignments.items():
        alignments = alignment_data.get("alignments", [])
        
        for alignment in alignments:
            operations = alignment.get("operations", [])
            
            for op_type, tool1, tool2 in operations:
                total_operations[op_type] += 1
                
                if op_type == "substitute":
                    substitutions[(tool1, tool2)] += 1
                elif op_type == "insert":
                    insertions[tool2] += 1
                elif op_type == "delete":
                    deletions[tool1] += 1
    
    return {
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "total_operations": total_operations
    }


def analyze_alignment_patterns_by_personality(conversations: List[Dict[str, Any]], trace_alignments: Dict[str, Any], user_personality: str = None, env_personality: str = None) -> Dict[str, Any]:
    """Analyze alignment patterns filtered by personality types."""
    if not trace_alignments:
        return {}
    
    # Filter conversations by personality - use names instead of descriptions
    filtered_conversations = conversations
    if user_personality and user_personality != "All":
        filtered_conversations = [c for c in filtered_conversations if c.get('user_personality_name', 'None') == user_personality]
    if env_personality and env_personality != "All":
        filtered_conversations = [c for c in filtered_conversations if c.get('environment_personality_name', 'None') == env_personality]
    
    # Get trace set IDs for filtered conversations
    relevant_trace_sets = set()
    for conv in filtered_conversations:
        if 'trace_set_id' in conv:
            relevant_trace_sets.add(conv['trace_set_id'])
    
    # Counters for different types of operations
    substitutions = Counter()
    insertions = Counter()
    deletions = Counter()
    total_operations = Counter()
    
    # Process relevant trace alignments only
    for trace_set_id, alignment_data in trace_alignments.items():
        if trace_set_id not in relevant_trace_sets:
            continue
            
        alignments = alignment_data.get("alignments", [])
        
        for alignment in alignments:
            operations = alignment.get("operations", [])
            
            for op_type, tool1, tool2 in operations:
                total_operations[op_type] += 1
                
                if op_type == "substitute":
                    substitutions[(tool1, tool2)] += 1
                elif op_type == "insert":
                    insertions[tool2] += 1
                elif op_type == "delete":
                    deletions[tool1] += 1
    
    return {
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "total_operations": total_operations,
        "conversation_count": len(filtered_conversations),
        "trace_set_count": len(relevant_trace_sets)
    }


def main():
    st.set_page_config(
        page_title="Conversation Viewer",
        page_icon="💬",
        layout="wide"
    )
    
    st.title("💬 Conversation Dataset Viewer")
    st.markdown("---")
    
    # Initialize session state for conversation selection
    if 'selected_conv_index' not in st.session_state:
        st.session_state.selected_conv_index = 0
    if 'show_conversation_details' not in st.session_state:
        st.session_state.show_conversation_details = False
    if 'selected_conversation' not in st.session_state:
        st.session_state.selected_conversation = None
    
    # Data loading options
    st.subheader("📂 Data Loading")
    
    # Add tabs for different loading methods
    load_tab1, load_tab2 = st.tabs(["📁 Load from Folder", "📎 Upload Files"])
    
    conversations = []
    trace_alignments = {}
    alignment_summary = []
    
    with load_tab1:
        st.markdown("**Load files automatically from a folder**")
        
        # Folder path input
        col1, col2 = st.columns([3, 1])
        
        with col1:
            folder_path = st.text_input(
                "Folder Path",
                help="Enter the path to the folder containing conversation data files"
            )
        
        with col2:
            if st.button("🔄 Reload", type="secondary"):
                if folder_path:
                    # Force reload by clearing cache
                    st.rerun()
                else:
                    st.error("Please enter a folder path")
        
        # Auto-load files when valid folder path is entered
        if folder_path and os.path.exists(folder_path):
            conversations, trace_alignments, alignment_summary = load_files_from_folder(folder_path)
        
        # Show detected files
        if folder_path and os.path.exists(folder_path):
            st.markdown("**📋 Files in folder:**")
            folder = Path(folder_path)
            json_files = list(folder.glob("*.json"))
            if json_files:
                for file in sorted(json_files):
                    file_size = file.stat().st_size
                    size_str = f"{file_size:,} bytes" if file_size < 1024*1024 else f"{file_size/(1024*1024):.1f} MB"
                    st.markdown(f"- `{file.name}` ({size_str})")
            else:
                st.markdown("- *No JSON files found*")
        elif folder_path:
            st.error(f"❌ Folder does not exist: {folder_path}")
    
    with load_tab2:
        st.markdown("**Upload individual files manually**")
        
        # File upload
        uploaded_file = st.file_uploader(
            "Upload conversations JSON file",
            type=['json'],
            help="Upload a JSON file containing conversation data",
            key="manual_conversations"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            alignment_file = st.file_uploader(
                "Upload trace alignments (optional)",
                type=['json'],
                help="Upload trace_alignments.json for trace set visualization",
                key="manual_alignment_file"
            )
        
        with col2:
            alignment_summary_file = st.file_uploader(
                "Upload alignment summary (optional)",
                type=['json'],
                help="Upload alignment_summary.json for trace set overview",
                key="manual_alignment_summary_file"
            )
        
        # Load uploaded files
        if uploaded_file is not None:
            try:
                conversations = json.load(uploaded_file)
                st.success(f"✅ Loaded {len(conversations)} conversations from uploaded file")
            except Exception as e:
                st.error(f"❌ Error loading uploaded file: {e}")
        
        if alignment_file is not None:
            try:
                trace_alignments = json.load(alignment_file)
                st.success(f"✅ Loaded alignments for {len(trace_alignments)} trace sets")
            except Exception as e:
                st.error(f"❌ Error loading alignment file: {e}")
        
        if alignment_summary_file is not None:
            try:
                alignment_summary = json.load(alignment_summary_file)
                st.success(f"✅ Loaded alignment summary for {len(alignment_summary)} trace sets")
            except Exception as e:
                st.error(f"❌ Error loading alignment summary file: {e}")
    
    # Show loading status
    if not conversations and not trace_alignments and not alignment_summary:
        st.info("💡 **Tip:** Use the folder loading tab to automatically detect and load files, or upload them manually in the upload tab.")
        return
    
    # Sidebar filters
    st.sidebar.header("Filters")
    
    # Get unique personalities - use names instead of descriptions
    user_personalities = list(set(conv.get('user_personality_name', 'None') for conv in conversations))
    env_personalities = list(set(conv.get('environment_personality_name', 'None') for conv in conversations))
    
    selected_user_personality = st.sidebar.selectbox(
        "User Personality",
        ["All"] + user_personalities,
        index=0
    )
    
    selected_env_personality = st.sidebar.selectbox(
        "Environment Personality", 
        ["All"] + env_personalities,
        index=0
    )
    
    # Filter conversations - use names for filtering
    filtered_conversations = conversations
    if selected_user_personality != "All":
        filtered_conversations = [c for c in filtered_conversations if c.get('user_personality_name', 'None') == selected_user_personality]
    if selected_env_personality != "All":
        filtered_conversations = [c for c in filtered_conversations if c.get('environment_personality_name', 'None') == selected_env_personality]
    
    st.sidebar.markdown(f"**Filtered: {len(filtered_conversations)} conversations**")
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Overview", "🔍 Browse Conversations", "📈 Similarity Analysis", "🧬 Trace Alignments", "👥 Personality Comparisons"])
    
    with tab1:
        st.header("Dataset Overview")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Conversations", len(conversations))
            st.metric("Filtered Conversations", len(filtered_conversations))
        
        with col2:
            st.metric("User Personalities", len(user_personalities))
            st.metric("Environment Personalities", len(env_personalities))
        
        with col3:
            # Calculate average tools
            avg_source_tools = sum(len(c.get('user_source', [])) for c in filtered_conversations) / len(filtered_conversations) if filtered_conversations else 0
            avg_used_tools = sum(len(c.get('used_tools', [])) for c in filtered_conversations) / len(filtered_conversations) if filtered_conversations else 0
            
            # Calculate average similarity
            avg_similarity = 0
            similarity_type = "Basic"
            if filtered_conversations:
                similarities = []
                for conv in filtered_conversations:
                    similarity, sim_type = get_similarity_score(conv, trace_alignments)
                    similarities.append(similarity)
                    similarity_type = sim_type  # Use the type from the last conversation (they should all be the same)
                avg_similarity = sum(similarities) / len(similarities)
            
            st.metric("Avg Source Tools", f"{avg_source_tools:.1f}")
            st.metric("Avg Used Tools", f"{avg_used_tools:.1f}")
            st.metric(f"Avg {similarity_type} Similarity", f"{avg_similarity:.3f}")
        
        with col4:
            # Calculate average goal achievement
            avg_goal_achievement = 0
            if filtered_conversations:
                scores = [get_goal_achievement_score(conv, trace_alignments) for conv in filtered_conversations]
                avg_goal_achievement = sum(scores) / len(scores) if scores else 0
            st.metric("Avg Goal Achievement", f"{avg_goal_achievement:.3f}")
        
        # Error Pattern Analysis
        if trace_alignments:
            st.markdown("---")
            st.header("🔍 Alignment Error Pattern Analysis")
            
            # Analyze alignment patterns
            pattern_analysis = analyze_alignment_patterns(trace_alignments)
            
            if pattern_analysis and any(pattern_analysis.values()):
                # Overall operation statistics
                total_ops = pattern_analysis["total_operations"]
                if total_ops:
                    st.subheader("📊 Operation Type Distribution")
                    
                    # Create columns for operation stats
                    op_col1, op_col2, op_col3, op_col4 = st.columns(4)
                    
                    with op_col1:
                        st.metric("Matches", total_ops.get("match", 0))
                    with op_col2:
                        st.metric("Substitutions", total_ops.get("substitute", 0))
                    with op_col3:
                        st.metric("Insertions", total_ops.get("insert", 0))
                    with op_col4:
                        st.metric("Deletions", total_ops.get("delete", 0))
                    
                    # Create a simple bar chart for operation distribution
                    op_data = {op_type: count for op_type, count in total_ops.items() if op_type != "match"}
                    if op_data:
                        st.bar_chart(op_data)
                
                # Error pattern details
                error_col1, error_col2, error_col3 = st.columns(3)
                
                with error_col1:
                    st.subheader("🔄 Most Common Substitutions")
                    substitutions = pattern_analysis["substitutions"]
                    if substitutions:
                        top_substitutions = substitutions.most_common(10)
                        for (from_tool, to_tool), count in top_substitutions:
                            st.markdown(f"**{count}x:** `{from_tool}` → `{to_tool}`")
                    else:
                        st.markdown("*No substitutions found*")
                
                with error_col2:
                    st.subheader("➕ Most Common Insertions")
                    insertions = pattern_analysis["insertions"]
                    if insertions:
                        top_insertions = insertions.most_common(10)
                        for tool, count in top_insertions:
                            st.markdown(f"**{count}x:** `{tool}`")
                    else:
                        st.markdown("*No insertions found*")
                
                with error_col3:
                    st.subheader("❌ Most Common Deletions")
                    deletions = pattern_analysis["deletions"]
                    if deletions:
                        top_deletions = deletions.most_common(10)
                        for tool, count in top_deletions:
                            st.markdown(f"**{count}x:** `{tool}`")
                    else:
                        st.markdown("*No deletions found*")
                
                # Summary insights
                st.subheader("💡 Pattern Insights")
                insights = []
                
                # Most problematic tools (frequently substituted or deleted)
                problematic_tools = Counter()
                for (from_tool, to_tool), count in substitutions.items():
                    problematic_tools[from_tool] += count
                for tool, count in deletions.items():
                    problematic_tools[tool] += count
                
                if problematic_tools:
                    most_problematic = problematic_tools.most_common(3)
                    insights.append(f"**Most problematic tools:** {', '.join([f'`{tool}` ({count} errors)' for tool, count in most_problematic])}")
                
                # Most commonly added tools
                if insertions:
                    most_added = insertions.most_common(3)
                    insights.append(f"**Most commonly added tools:** {', '.join([f'`{tool}` ({count}x)' for tool, count in most_added])}")
                
                # Error rate
                total_error_ops = sum(count for op_type, count in total_ops.items() if op_type != "match")
                total_all_ops = sum(total_ops.values())
                if total_all_ops > 0:
                    error_rate = (total_error_ops / total_all_ops) * 100
                    insights.append(f"**Overall error rate:** {error_rate:.1f}% ({total_error_ops}/{total_all_ops} operations)")
                
                for insight in insights:
                    st.markdown(insight)
            else:
                st.info("No alignment error patterns found in the dataset.")
        else:
            st.info("💡 Upload trace alignment data to see error pattern analysis.")
    
    with tab2:
        st.header("Browse Conversations")
        
        if not filtered_conversations:
            st.warning("No conversations match the current filters.")
            return
        
        # Calculate similarities and create sorted list
        conversations_with_scores = []
        for i, conv in enumerate(filtered_conversations):
            similarity, similarity_type = get_similarity_score(conv, trace_alignments)
            goal_achievement = get_goal_achievement_score(conv, trace_alignments)
            conversations_with_scores.append({
                'original_index': i,
                'conversation': conv,
                'similarity': similarity,
                'goal_achievement': goal_achievement,
                'similarity_type': similarity_type
            })
        
        # Sort by similarity score (ascending - worst to best)
        conversations_with_scores.sort(key=lambda x: x['similarity'])
        
        # Conversation selector
        conv_index = st.selectbox(
            "Select Conversation",
            range(len(conversations_with_scores)),
            format_func=lambda x: f"Conversation {conversations_with_scores[x]['original_index']+1} (Sim: {conversations_with_scores[x]['similarity']:.2f}, Goal: {conversations_with_scores[x]['goal_achievement']:.2f}): {conversations_with_scores[x]['conversation']['user_goal'][:50]}...",
            index=st.session_state.selected_conv_index if st.session_state.selected_conv_index < len(conversations_with_scores) else 0
        )
        
        conv = conversations_with_scores[conv_index]['conversation']
        goal_achievement = conversations_with_scores[conv_index]['goal_achievement']
        
        # Display conversation details
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Conversation Details")
            
            # User goal
            st.markdown("**User Goal:**")
            st.write(conv['user_goal'])
            
            # History
            st.markdown("**Conversation History:**")
            for i, message in enumerate(conv.get('history', [])):
                role = message.get('role', 'unknown')
                content = message.get('content', '')
                tool_calls = message.get('tool_calls', [])
                tool_call_id = message.get('tool_call_id', '')
                
                if role == 'system':
                    # Skip system messages
                    continue
                elif role == 'user':
                    st.chat_message("user").write(content)
                elif role == 'assistant':
                    with st.chat_message("assistant"):
                        if content:
                            st.write(content)
                        
                        # Display tool calls if present
                        if tool_calls:
                            st.markdown("**🔧 Tool Calls:**")
                            for tool_call in tool_calls:
                                tool_name = tool_call.get('function', {}).get('name', 'unknown')
                                tool_args = tool_call.get('function', {}).get('arguments', '{}')
                                tool_id = tool_call.get('id', 'unknown')
                                
                                # Try to format JSON arguments nicely
                                try:
                                    parsed_args = json.loads(tool_args)
                                    formatted_args = json.dumps(parsed_args, indent=2)
                                except:
                                    formatted_args = tool_args
                                
                                with st.expander(f"🔧 {tool_name} ({tool_id[:8]}...)", expanded=True):
                                    st.code(formatted_args, language="json")
                elif role == 'tool':
                    # Tool result - format nicely with indentation
                    tool_name = message.get('name', 'unknown_tool')
                    with st.container():
                        st.markdown(f"**🔧 Tool Result: `{tool_name}`** `{tool_call_id[:8] if tool_call_id else 'unknown'}...`")
                        
                        # Format tool result content with proper indentation
                        if content:
                            # Split content into lines and add proper indentation
                            lines = content.split('\n')
                            formatted_content = ""
                            for line in lines:
                                if line.strip():
                                    formatted_content += f"    {line}\n"
                                else:
                                    formatted_content += "\n"
                            
                            st.code(formatted_content.rstrip(), language="text")
                        else:
                            st.code("(No content)", language="text")
                else:
                    st.write(f"**{role.title()}:** {content}")
        
        with col2:
            st.subheader("Metadata")
            
            # Tools
            user_source_tools = [tool.get('name', '') for tool in conv.get('user_source', [])]
            used_tools = conv.get('used_tools', [])
            similarity, similarity_type = get_similarity_score(conv, trace_alignments)
            
            st.markdown("**Available Tools:**")
            for tool in user_source_tools:
                st.code(tool)
            
            st.markdown("**Used Tools:**")
            for tool in used_tools:
                st.code(tool)
            
            st.metric(f"{similarity_type} Similarity", f"{similarity:.3f}")
            st.metric("Goal Achievement", f"{goal_achievement:.3f}")
            
            # Personalities
            st.markdown("**User Personality:**")
            user_personality_name = conv.get('user_personality_name', 'None')
            st.write(user_personality_name if user_personality_name else 'None')
            
            st.markdown("**Environment Personality:**")
            env_personality_name = conv.get('environment_personality_name', 'None')
            st.write(env_personality_name if env_personality_name else 'None')
    
    with tab3:
        st.header("Similarity Analysis")
        
        if not filtered_conversations:
            st.warning("No conversations match the current filters.")
            return
        
        # Calculate similarities for filtered data
        similarities = []
        similarity_type = "Basic"
        goal_achievements = []
        for i, conv in enumerate(filtered_conversations):
            similarity, sim_type = get_similarity_score(conv, trace_alignments)
            similarity_type = sim_type  # Use the type from conversations
            goal_achievement = get_goal_achievement_score(conv, trace_alignments)
            similarities.append({
                'similarity': similarity,
                'goal_achievement': goal_achievement,
                'user_personality': conv.get('user_personality_name', 'None') or 'None',
                'environment_personality': conv.get('environment_personality_name', 'None') or 'None',
                'user_goal': conv['user_goal'][:100] + "..." if len(conv['user_goal']) > 100 else conv['user_goal'],
                'original_index': i
            })
            goal_achievements.append(goal_achievement)
        
        # Create DataFrame
        df = pd.DataFrame(similarities)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"{similarity_type} Similarity Distribution")
            # Create histogram using pandas and streamlit
            hist_data = np.histogram(df['similarity'], bins=20)
            hist_df = pd.DataFrame({
                'similarity_range': [f"{hist_data[1][i]:.2f}-{hist_data[1][i+1]:.2f}" for i in range(len(hist_data[0]))],
                'count': hist_data[0]
            })
            st.bar_chart(hist_df.set_index('similarity_range'))
            
            st.metric(f"Mean {similarity_type} Similarity", f"{df['similarity'].mean():.3f}")
            st.metric(f"Std {similarity_type} Similarity", f"{df['similarity'].std():.3f}")
            st.metric(f"Mean Goal Achievement", f"{df['goal_achievement'].mean():.3f}")
            st.metric(f"Std Goal Achievement", f"{df['goal_achievement'].std():.3f}")
        
        with col2:
            st.subheader("Top/Bottom Similarities and Goal Achievement")
            
            # Top similarities
            st.markdown("**Highest Similarities:**")
            top_sims = df.nlargest(5, 'similarity')
            for idx, row in top_sims.iterrows():
                if st.button(f"Conversation {row['original_index']+1}: Sim {row['similarity']:.3f}, Goal {row['goal_achievement']:.3f} - {row['user_goal']}", 
                           key=f"view_top_{idx}", 
                           help="Click to view conversation details"):
                    st.session_state.selected_conversation = filtered_conversations[row['original_index']]
                    st.session_state.show_conversation_details = True
            
            # Top goal achievement
            st.markdown("**Highest Goal Achievement:**")
            top_goal = df.nlargest(5, 'goal_achievement')
            for idx, row in top_goal.iterrows():
                if st.button(f"Conversation {row['original_index']+1}: Goal {row['goal_achievement']:.3f}, Sim {row['similarity']:.3f} - {row['user_goal']}", 
                           key=f"view_top_goal_{idx}", 
                           help="Click to view conversation details"):
                    st.session_state.selected_conversation = filtered_conversations[row['original_index']]
                    st.session_state.show_conversation_details = True
            
            # Bottom similarities
            st.markdown("**Lowest Similarities:**")
            bottom_sims = df.nsmallest(5, 'similarity')
            for idx, row in bottom_sims.iterrows():
                if st.button(f"Conversation {row['original_index']+1}: Sim {row['similarity']:.3f}, Goal {row['goal_achievement']:.3f} - {row['user_goal']}", 
                           key=f"view_bottom_{idx}", 
                           help="Click to view conversation details"):
                    st.session_state.selected_conversation = filtered_conversations[row['original_index']]
                    st.session_state.show_conversation_details = True
            
            # Bottom goal achievement
            st.markdown("**Lowest Goal Achievement:**")
            bottom_goal = df.nsmallest(5, 'goal_achievement')
            for idx, row in bottom_goal.iterrows():
                if st.button(f"Conversation {row['original_index']+1}: Goal {row['goal_achievement']:.3f}, Sim {row['similarity']:.3f} - {row['user_goal']}", 
                           key=f"view_bottom_goal_{idx}", 
                           help="Click to view conversation details"):
                    st.session_state.selected_conversation = filtered_conversations[row['original_index']]
                    st.session_state.show_conversation_details = True
        
        # Show conversation details if a conversation is selected
        if st.session_state.show_conversation_details and st.session_state.selected_conversation:
            st.markdown("---")
            st.subheader("📖 Conversation Details")
            
            # Add a close button
            if st.button("❌ Close", key="close_details", help="Close conversation details"):
                st.session_state.show_conversation_details = False
                st.session_state.selected_conversation = None
            
            conv = st.session_state.selected_conversation
            
            # Display conversation details in two columns
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # User goal
                st.markdown("**User Goal:**")
                st.write(conv['user_goal'])
                
                # History
                st.markdown("**Conversation History:**")
                for i, message in enumerate(conv.get('history', [])):
                    role = message.get('role', 'unknown')
                    content = message.get('content', '')
                    tool_calls = message.get('tool_calls', [])
                    tool_call_id = message.get('tool_call_id', '')
                    
                    if role == 'system':
                        # Skip system messages
                        continue
                    elif role == 'user':
                        st.chat_message("user").write(content)
                    elif role == 'assistant':
                        with st.chat_message("assistant"):
                            if content:
                                st.write(content)
                            
                            # Display tool calls if present
                            if tool_calls:
                                st.markdown("**🔧 Tool Calls:**")
                                for tool_call in tool_calls:
                                    tool_name = tool_call.get('function', {}).get('name', 'unknown')
                                    tool_args = tool_call.get('function', {}).get('arguments', '{}')
                                    tool_id = tool_call.get('id', 'unknown')
                                    
                                    # Try to format JSON arguments nicely
                                    try:
                                        parsed_args = json.loads(tool_args)
                                        formatted_args = json.dumps(parsed_args, indent=2)
                                    except:
                                        formatted_args = tool_args
                                    
                                    with st.expander(f"🔧 {tool_name} ({tool_id[:8]}...)", expanded=True):
                                        st.code(formatted_args, language="json")
                    elif role == 'tool':
                        # Tool result - format nicely with indentation
                        tool_name = message.get('name', 'unknown_tool')
                        with st.container():
                            st.markdown(f"**🔧 Tool Result: `{tool_name}`** `{tool_call_id[:8] if tool_call_id else 'unknown'}...`")
                            
                            # Format tool result content with proper indentation
                            if content:
                                # Split content into lines and add proper indentation
                                lines = content.split('\n')
                                formatted_content = ""
                                for line in lines:
                                    if line.strip():
                                        formatted_content += f"    {line}\n"
                                    else:
                                        formatted_content += "\n"
                                
                                st.code(formatted_content.rstrip(), language="text")
                            else:
                                st.code("(No content)", language="text")
                    else:
                        st.write(f"**{role.title()}:** {content}")
            
            with col2:
                st.markdown("**Metadata**")
                
                # Tools
                user_source_tools = [tool.get('name', '') for tool in conv.get('user_source', [])]
                used_tools = conv.get('used_tools', [])
                similarity, similarity_type = get_similarity_score(conv, trace_alignments)
                
                st.markdown("**Available Tools:**")
                for tool in user_source_tools:
                    st.code(tool)
                
                st.markdown("**Used Tools:**")
                for tool in used_tools:
                    st.code(tool)
                
                st.metric(f"{similarity_type} Similarity", f"{similarity:.3f}")
                
                # Personalities
                st.markdown("**User Personality:**")
                user_personality_name = conv.get('user_personality_name', 'None')
                st.write(user_personality_name if user_personality_name else 'None')
                
                st.markdown("**Environment Personality:**")
                env_personality_name = conv.get('environment_personality_name', 'None')
                st.write(env_personality_name if env_personality_name else 'None')
                
                # Additional trace-specific metadata
                if 'trace_set_id' in conv:
                    st.markdown("**Trace Information:**")
                    st.write(f"Trace Set ID: {conv.get('trace_set_id', 'N/A')}")
                    st.write(f"Instance ID: {conv.get('instantiation_id', 'N/A')}")


    with tab4:
        st.header("Trace Alignments")
        
        if not trace_alignments and not alignment_summary:
            st.warning("No trace alignment data available. Upload trace_alignments.json and alignment_summary.json to view trace set visualizations.")
            return
        
        if not conversations:
            st.warning("No conversations loaded. Please upload conversations to view trace alignments.")
            return
        
        # Show overview if we have alignment summary
        if alignment_summary:
            st.subheader("📊 Trace Set Overview")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Trace Sets", len(alignment_summary))
                avg_instantiations = sum(ts["instantiation_count"] for ts in alignment_summary) / len(alignment_summary) if alignment_summary else 0
                st.metric("Avg Instantiations", f"{avg_instantiations:.1f}")
            
            with col2:
                avg_similarity = sum(ts["avg_similarity"] for ts in alignment_summary) / len(alignment_summary) if alignment_summary else 0
                min_similarity = min(ts["min_similarity"] for ts in alignment_summary) if alignment_summary else 0
                st.metric("Avg Alignment Similarity", f"{avg_similarity:.3f}")
                st.metric("Min Alignment Similarity", f"{min_similarity:.3f}")
            
            with col3:
                # Calculate variety metrics
                unique_personalities = len(set(ts.get("user_personality_name", 'None') or 'None' for ts in alignment_summary))
                unique_env_personalities = len(set(ts.get("environment_personality_name", 'None') or 'None' for ts in alignment_summary))
                st.metric("User Personalities", unique_personalities)
                st.metric("Env Personalities", unique_env_personalities)
            
            with col4:
                avg_goal_achievement = sum(ts.get("avg_goal_achievement", 0) for ts in alignment_summary) / len(alignment_summary) if alignment_summary else 0
                min_goal_achievement = min(ts.get("min_goal_achievement", 0) for ts in alignment_summary) if alignment_summary else 0
                st.metric("Avg Goal Achievement", f"{avg_goal_achievement:.3f}")
                st.metric("Min Goal Achievement", f"{min_goal_achievement:.3f}")
            
            # Trace set selector
            st.subheader("🔍 Explore Trace Sets")
            
            if alignment_summary:
                # Sort by average similarity (lowest first - most problematic)
                sorted_trace_sets = sorted(alignment_summary, key=lambda x: x["avg_similarity"])
                
                trace_set_index = st.selectbox(
                    "Select Trace Set",
                    range(len(sorted_trace_sets)),
                    format_func=lambda x: f"Set {x+1}: {sorted_trace_sets[x]['user_goal'][:50]}... (Avg Sim: {sorted_trace_sets[x]['avg_similarity']:.3f}, {sorted_trace_sets[x]['instantiation_count']} instances)",
                    key="trace_set_selector"
                )
                
                selected_trace_set = sorted_trace_sets[trace_set_index]
                trace_set_id = selected_trace_set["trace_set_id"]
                
                # Display trace set details
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("🧬 Trace Alignment Flow Visualization")
                    
                    # Get alignment data for this trace set
                    if trace_set_id in trace_alignments:
                        alignment_data = trace_alignments[trace_set_id]
                        
                        # Create and display the network graph visualization
                        img_base64 = create_trace_alignment_graph(alignment_data)
                        st.image(f"data:image/png;base64,{img_base64}", use_container_width=True)
                        
                        st.markdown("**Alignment Graph Visualization Legend:**")
                        st.markdown("- **Grey nodes**: START and END nodes (sequence boundaries)")
                        st.markdown("- **Blue nodes**: Reference sequence tools")
                        st.markdown("- **Red nodes**: Sequence variations (substitutions/insertions)")
                        st.markdown("- **Blue edges**: Reference backbone and start/end connections to reference nodes")
                        st.markdown("- **Red edges**: Sequence variations and start/end connections to variation nodes")
                        st.markdown("- **Edge thickness**: Number of traces using that path")
                        st.markdown("- **Node labels**: Tool names (simplified)")
                        
                        # Expandable detailed operations view
                        with st.expander("📋 Detailed Alignment Operations", expanded=False):
                            st.markdown("**Reference Sequence:**")
                            reference_display = " → ".join(alignment_data["reference_sequence"]) if alignment_data["reference_sequence"] else "(empty)"
                            st.code(reference_display)
                            
                            # Get goal achievement results for this trace set
                            goal_results = alignment_data.get("goal_achievement_results", [])
                            
                            for i, alignment in enumerate(alignment_data["alignments"]):
                                # Get goal achievement score for this instance
                                goal_score = 0.0
                                if i < len(goal_results):
                                    goal_score = goal_results[i].get("score", 0.0)
                                
                                st.markdown(f"**Instance {i} Operations (Distance: {alignment['distance']:.3f}, Goal: {goal_score:.3f}):**")
                                operations = alignment["operations"]
                                for j, (op_type, tool1, tool2) in enumerate(operations):
                                    if op_type == "match":
                                        st.markdown(f"  ✅ **Step {j+1}:** Match `{tool1}`")
                                    elif op_type == "substitute":
                                        st.markdown(f"  🔄 **Step {j+1}:** Substitute `{tool1}` → `{tool2}`")
                                    elif op_type == "delete":
                                        st.markdown(f"  ❌ **Step {j+1}:** Delete `{tool1}`")
                                    elif op_type == "insert":
                                        st.markdown(f"  ➕ **Step {j+1}:** Insert `{tool2}`")
                                st.markdown("---")
                    else:
                        st.warning(f"No alignment data found for trace set {trace_set_id}")
                
                with col2:
                    st.subheader("📝 Trace Set Metadata")
                    
                    st.markdown("**User Goal:**")
                    st.write(selected_trace_set["user_goal"])
                    
                    st.markdown("**Expected Tool Sequence:**")
                    for tool in selected_trace_set["expected_tools"]:
                        st.code(tool)
                    
                    st.markdown("**Personalities:**")
                    user_personality_name = selected_trace_set.get('user_personality_name', 'None')
                    env_personality_name = selected_trace_set.get('environment_personality_name', 'None')
                    st.write(f"User: {user_personality_name if user_personality_name else 'None'}")
                    st.write(f"Environment: {env_personality_name if env_personality_name else 'None'}")
                    
                    st.markdown("**Statistics:**")
                    st.metric("Instantiations", selected_trace_set["instantiation_count"])
                    st.metric("Avg Similarity", f"{selected_trace_set['avg_similarity']:.3f}")
                    st.metric("Max Similarity", f"{selected_trace_set['max_similarity']:.3f}")
                    st.metric("Min Similarity", f"{selected_trace_set['min_similarity']:.3f}")
                    
                    # Show individual conversations
                    st.markdown("**View Individual Conversations:**")
                    conversation_ids = selected_trace_set.get("conversation_ids", [])
                    for i, conv_id in enumerate(conversation_ids):
                        if conv_id < len(conversations):
                            conv = conversations[conv_id]
                            used_tools_display = " → ".join(conv["used_tools"]) if conv["used_tools"] else "(no tools)"
                            if st.button(f"Instance {i}: {used_tools_display}", key=f"view_conv_{conv_id}"):
                                st.session_state.selected_conversation = conv
                                st.session_state.show_conversation_details = True
        
        # Show conversation details if selected from trace alignment view
        if st.session_state.show_conversation_details and st.session_state.selected_conversation:
            st.markdown("---")
            st.subheader("📖 Selected Conversation Details")
            
            if st.button("❌ Close", key="close_details_trace", help="Close conversation details"):
                st.session_state.show_conversation_details = False
                st.session_state.selected_conversation = None
            
            conv = st.session_state.selected_conversation
            
            # Display conversation details in two columns (same as Browse Conversations tab)
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # User goal
                st.markdown("**User Goal:**")
                st.write(conv['user_goal'])
                
                # History - Full conversation display like in Browse Conversations tab
                st.markdown("**Conversation History:**")
                for i, message in enumerate(conv.get('history', [])):
                    role = message.get('role', 'unknown')
                    content = message.get('content', '')
                    tool_calls = message.get('tool_calls', [])
                    tool_call_id = message.get('tool_call_id', '')
                    
                    if role == 'system':
                        # Skip system messages
                        continue
                    elif role == 'user':
                        st.chat_message("user").write(content)
                    elif role == 'assistant':
                        with st.chat_message("assistant"):
                            if content:
                                st.write(content)
                            
                            # Display tool calls if present
                            if tool_calls:
                                st.markdown("**🔧 Tool Calls:**")
                                for tool_call in tool_calls:
                                    tool_name = tool_call.get('function', {}).get('name', 'unknown')
                                    tool_args = tool_call.get('function', {}).get('arguments', '{}')
                                    tool_id = tool_call.get('id', 'unknown')
                                    
                                    # Try to format JSON arguments nicely
                                    try:
                                        parsed_args = json.loads(tool_args)
                                        formatted_args = json.dumps(parsed_args, indent=2)
                                    except:
                                        formatted_args = tool_args
                                    
                                    with st.expander(f"🔧 {tool_name} ({tool_id[:8]}...)", expanded=True):
                                        st.code(formatted_args, language="json")
                    elif role == 'tool':
                        # Tool result - format nicely with indentation
                        tool_name = message.get('name', 'unknown_tool')
                        with st.container():
                            st.markdown(f"**🔧 Tool Result: `{tool_name}`** `{tool_call_id[:8] if tool_call_id else 'unknown'}...`")
                            
                            # Format tool result content with proper indentation
                            if content:
                                # Split content into lines and add proper indentation
                                lines = content.split('\n')
                                formatted_content = ""
                                for line in lines:
                                    if line.strip():
                                        formatted_content += f"    {line}\n"
                                    else:
                                        formatted_content += "\n"
                                
                                st.code(formatted_content.rstrip(), language="text")
                            else:
                                st.code("(No content)", language="text")
                    else:
                        st.write(f"**{role.title()}:** {content}")
            
            with col2:
                st.subheader("Metadata")
                
                # Tools
                user_source_tools = [tool.get('name', '') for tool in conv.get('user_source', [])]
                used_tools = conv.get('used_tools', [])
                similarity, similarity_type = get_similarity_score(conv, trace_alignments)
                
                st.markdown("**Available Tools:**")
                for tool in user_source_tools:
                    st.code(tool)
                
                st.markdown("**Used Tools:**")
                for tool in used_tools:
                    st.code(tool)
                
                st.metric(f"{similarity_type} Similarity", f"{similarity:.3f}")
                
                # Personalities
                st.markdown("**User Personality:**")
                user_personality_name = conv.get('user_personality_name', 'None')
                st.write(user_personality_name if user_personality_name else 'None')
                
                st.markdown("**Environment Personality:**")
                env_personality_name = conv.get('environment_personality_name', 'None')
                st.write(env_personality_name if env_personality_name else 'None')
                
                # Additional trace-specific metadata
                if 'trace_set_id' in conv:
                    st.markdown("**Trace Information:**")
                    st.write(f"Trace Set ID: {conv.get('trace_set_id', 'N/A')}")
                    st.write(f"Instance ID: {conv.get('instantiation_id', 'N/A')}")


    with tab5:
        st.header("👥 Personality Comparisons")
        
        if not trace_alignments:
            st.warning("No trace alignment data available. Upload trace_alignments.json to view personality comparisons.")
            return
        
        if not conversations:
            st.warning("No conversations loaded. Please upload conversations to view personality comparisons.")
            return
        
        st.markdown("Compare alignment error patterns across different user and environment personalities.")
        
        # Filter controls
        st.subheader("🎛️ Filtering Controls")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            selected_user_personalities = st.multiselect(
                "User Personalities",
                ["All"] + user_personalities,
                default=["All"],
                help="Select user personalities to compare"
            )
        
        with filter_col2:
            selected_env_personalities = st.multiselect(
                "Environment Personalities", 
                ["All"] + env_personalities,
                default=["All"],
                help="Select environment personalities to compare"
            )
        
        with filter_col3:
            comparison_type = st.radio(
                "Comparison Type",
                ["User Personalities", "Environment Personalities", "User vs Environment"],
                help="Choose what to compare"
            )
        
        # Generate comparison data
        comparison_data = {}
        
        if comparison_type == "User Personalities":
            personalities_to_compare = [p for p in selected_user_personalities if p in user_personalities] if "All" not in selected_user_personalities else user_personalities
            
            for personality in personalities_to_compare:
                patterns = analyze_alignment_patterns_by_personality(conversations, trace_alignments, user_personality=personality)
                comparison_data[f"User: {personality}"] = patterns
        
        elif comparison_type == "Environment Personalities":
            personalities_to_compare = [p for p in selected_env_personalities if p in env_personalities] if "All" not in selected_env_personalities else env_personalities
            
            for personality in personalities_to_compare:
                patterns = analyze_alignment_patterns_by_personality(conversations, trace_alignments, env_personality=personality)
                comparison_data[f"Env: {personality}"] = patterns
        
        else:  # User vs Environment
            # Compare each user personality with each environment personality
            user_ps = [p for p in selected_user_personalities if p in user_personalities] if "All" not in selected_user_personalities else user_personalities
            env_ps = [p for p in selected_env_personalities if p in env_personalities] if "All" not in selected_env_personalities else env_personalities
            
            for user_p in user_ps:
                for env_p in env_ps:
                    patterns = analyze_alignment_patterns_by_personality(conversations, trace_alignments, user_personality=user_p, env_personality=env_p)
                    if patterns.get("conversation_count", 0) > 0:  # Only include combinations with data
                        comparison_data[f"U:{user_p} + E:{env_p}"] = patterns
        
        if not comparison_data:
            st.warning("No data available for the selected personality combinations.")
            return
        
        # Display comparison results
        st.markdown("---")
        st.subheader("📊 Comparison Results")
        
        # Overview metrics
        st.subheader("📈 Overview Metrics")
        
        metrics_data = []
        for group_name, patterns in comparison_data.items():
            total_ops = patterns.get("total_operations", Counter())
            conversation_count = patterns.get("conversation_count", 0)
            trace_set_count = patterns.get("trace_set_count", 0)
            
            total_error_ops = sum(count for op_type, count in total_ops.items() if op_type != "match")
            total_all_ops = sum(total_ops.values())
            error_rate = (total_error_ops / total_all_ops * 100) if total_all_ops > 0 else 0
            
            # Calculate mean goal achievement for this group
            group_goal_scores = []
            for conv in conversations:
                if group_name.endswith(conv.get('user_personality_name', 'None')) or group_name.endswith(conv.get('environment_personality_name', 'None')):
                    group_goal_scores.append(get_goal_achievement_score(conv, trace_alignments))
            mean_goal_achievement = sum(group_goal_scores) / len(group_goal_scores) if group_goal_scores else 0
            
            metrics_data.append({
                "Group": group_name,
                "Conversations": conversation_count,
                "Trace Sets": trace_set_count,
                "Total Operations": total_all_ops,
                "Error Rate (%)": round(error_rate, 1),
                "Substitutions": total_ops.get("substitute", 0),
                "Insertions": total_ops.get("insert", 0),
                "Deletions": total_ops.get("delete", 0),
                "Mean Goal Achievement": round(mean_goal_achievement, 3)
            })
        
        if metrics_data:
            metrics_df = pd.DataFrame(metrics_data)
            st.dataframe(metrics_df, use_container_width=True)
        
        # Detailed pattern comparisons
        st.subheader("🔍 Detailed Pattern Analysis")
        
        comparison_tabs = st.tabs(["🔄 Substitutions", "➕ Insertions", "❌ Deletions"])
        
        with comparison_tabs[0]:
            st.markdown("**Most Common Substitutions by Group**")
            
            for group_name, patterns in comparison_data.items():
                substitutions = patterns.get("substitutions", Counter())
                if substitutions:
                    st.markdown(f"**{group_name}:**")
                    top_substitutions = substitutions.most_common(5)
                    for (from_tool, to_tool), count in top_substitutions:
                        st.markdown(f"  • **{count}x:** `{from_tool}` → `{to_tool}`")
                else:
                    st.markdown(f"**{group_name}:** *No substitutions*")
                st.markdown("")
        
        with comparison_tabs[1]:
            st.markdown("**Most Common Insertions by Group**")
            
            for group_name, patterns in comparison_data.items():
                insertions = patterns.get("insertions", Counter())
                if insertions:
                    st.markdown(f"**{group_name}:**")
                    top_insertions = insertions.most_common(5)
                    for tool, count in top_insertions:
                        st.markdown(f"  • **{count}x:** `{tool}`")
                else:
                    st.markdown(f"**{group_name}:** *No insertions*")
                st.markdown("")
        
        with comparison_tabs[2]:
            st.markdown("**Most Common Deletions by Group**")
            
            for group_name, patterns in comparison_data.items():
                deletions = patterns.get("deletions", Counter())
                if deletions:
                    st.markdown(f"**{group_name}:**")
                    top_deletions = deletions.most_common(5)
                    for tool, count in top_deletions:
                        st.markdown(f"  • **{count}x:** `{tool}`")
                else:
                    st.markdown(f"**{group_name}:** *No deletions*")
                st.markdown("")
        
        # Insights and recommendations
        st.subheader("💡 Insights & Recommendations")
        
        insights = []
        
        # Find personality with highest error rate
        if len(comparison_data) > 1:
            error_rates = {}
            for group_name, patterns in comparison_data.items():
                total_ops = patterns.get("total_operations", Counter())
                total_error_ops = sum(count for op_type, count in total_ops.items() if op_type != "match")
                total_all_ops = sum(total_ops.values())
                error_rate = (total_error_ops / total_all_ops * 100) if total_all_ops > 0 else 0
                error_rates[group_name] = error_rate
            
            if error_rates:
                highest_error_group = max(error_rates.items(), key=lambda x: x[1])
                lowest_error_group = min(error_rates.items(), key=lambda x: x[1])
                
                insights.append(f"**Highest error rate:** {highest_error_group[0]} ({highest_error_group[1]:.1f}%)")
                insights.append(f"**Lowest error rate:** {lowest_error_group[0]} ({lowest_error_group[1]:.1f}%)")
        
        # Find most problematic tools across groups
        all_problematic_tools = Counter()
        for patterns in comparison_data.values():
            substitutions = patterns.get("substitutions", Counter())
            deletions = patterns.get("deletions", Counter())
            
            for (from_tool, to_tool), count in substitutions.items():
                all_problematic_tools[from_tool] += count
            for tool, count in deletions.items():
                all_problematic_tools[tool] += count
        
        if all_problematic_tools:
            most_problematic = all_problematic_tools.most_common(3)
            insights.append(f"**Most problematic tools overall:** {', '.join([f'`{tool}` ({count} errors)' for tool, count in most_problematic])}")
        
        # Find most commonly added tools across groups
        all_insertions = Counter()
        for patterns in comparison_data.values():
            insertions = patterns.get("insertions", Counter())
            for tool, count in insertions.items():
                all_insertions[tool] += count
        
        if all_insertions:
            most_added = all_insertions.most_common(3)
            insights.append(f"**Most commonly added tools overall:** {', '.join([f'`{tool}` ({count}x)' for tool, count in most_added])}")
        
        for insight in insights:
            st.markdown(insight)
        
        if not insights:
            st.info("Analyze multiple personality groups to see comparative insights.")


if __name__ == "__main__":
    main() 