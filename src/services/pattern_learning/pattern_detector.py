"""
Pattern Detection and Analysis
Analyzes tool sequences to identify frequently occurring patterns
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from models.tool_pattern_models import (
    learned_tool_patterns_collection,
    tool_execution_sequences_collection
)
from globals import logger


# Configuration
MIN_PATTERN_OCCURRENCES = 5  # Minimum times a pattern must occur to be considered
MIN_CONFIDENCE = 0.7  # Minimum confidence score (0-1)
ANALYSIS_WINDOW_DAYS = 7  # Days to look back for pattern analysis


async def detect_patterns(org_id: str, bridge_id: str, force_update: bool = False) -> list:
    """
    Detect and store frequently occurring tool patterns
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        force_update: Force re-analysis even if recently analyzed
    
    Returns:
        List of detected patterns
    """
    try:
        logger.info(f"Starting pattern detection for bridge {bridge_id}")
        
        # Get sequences from the analysis window
        cutoff_date = datetime.utcnow() - timedelta(days=ANALYSIS_WINDOW_DAYS)
        
        sequences = await tool_execution_sequences_collection.find({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "timestamp": {"$gte": cutoff_date},
            "sequence_length": {"$gte": 2}
        }).to_list(length=None)
        
        if not sequences:
            logger.info("No sequences found for pattern detection")
            return []
        
        # Analyze sequences
        pattern_data = _analyze_sequences_for_patterns(sequences)
        
        # Filter patterns by threshold
        detected_patterns = []
        
        for pattern_hash, data in pattern_data.items():
            if data["frequency"] < MIN_PATTERN_OCCURRENCES:
                continue
            
            confidence = _calculate_confidence(data, sequences)
            
            if confidence < MIN_CONFIDENCE:
                continue
            
            # Infer data flow between tools
            data_flow = _infer_data_flow(data["occurrences"])
            
            # Calculate potential savings
            avg_latency = data["total_latency"] / data["frequency"]
            # Estimate 2 AI calls saved per execution (conservative)
            estimated_savings_ms = 2000 * 2  # ~2s per AI call
            
            pattern = {
                "org_id": org_id,
                "bridge_id": bridge_id,
                "pattern_hash": pattern_hash,
                "tools": data["tool_names"],
                "frequency": data["frequency"],
                "confidence": confidence,
                "data_flow": data_flow,
                "avg_latency_ms": avg_latency,
                "estimated_savings_ms": estimated_savings_ms,
                "first_seen": data["first_seen"],
                "last_seen": data["last_seen"],
                "status": "pending_approval",
                "chain_id": None,
                "detected_at": datetime.utcnow()
            }
            
            # Upsert pattern to database
            await learned_tool_patterns_collection.update_one(
                {
                    "org_id": org_id,
                    "bridge_id": bridge_id,
                    "pattern_hash": pattern_hash
                },
                {"$set": pattern},
                upsert=True
            )
            
            detected_patterns.append(pattern)
        
        logger.info(f"Detected {len(detected_patterns)} patterns for bridge {bridge_id}")
        
        return detected_patterns
        
    except Exception as error:
        logger.error(f"Error in pattern detection: {error}")
        return []


def _analyze_sequences_for_patterns(sequences: list) -> dict:
    """
    Analyze sequences and group by pattern
    
    Returns:
        Dictionary mapping pattern_hash to pattern data
    """
    pattern_data = defaultdict(lambda: {
        "frequency": 0,
        "tool_names": [],
        "occurrences": [],
        "total_latency": 0,
        "first_seen": None,
        "last_seen": None
    })
    
    for seq in sequences:
        pattern_hash = seq.get("pattern_hash")
        if not pattern_hash:
            continue
        
        data = pattern_data[pattern_hash]
        data["frequency"] += 1
        data["tool_names"] = seq.get("tool_names", [])
        data["occurrences"].append(seq)
        data["total_latency"] += seq.get("total_latency_ms", 0)
        
        timestamp = seq.get("timestamp")
        if timestamp:
            if data["first_seen"] is None or timestamp < data["first_seen"]:
                data["first_seen"] = timestamp
            if data["last_seen"] is None or timestamp > data["last_seen"]:
                data["last_seen"] = timestamp
    
    return dict(pattern_data)


def _calculate_confidence(pattern_data: dict, all_sequences: list) -> float:
    """
    Calculate confidence score for a pattern
    
    Confidence is based on:
    - Frequency (how often it occurs)
    - Consistency (how similar the occurrences are)
    - Recency (when it last occurred)
    
    Returns:
        Confidence score between 0 and 1
    """
    frequency = pattern_data["frequency"]
    total_sequences = len(all_sequences)
    
    # Frequency score (normalized)
    frequency_score = min(frequency / (MIN_PATTERN_OCCURRENCES * 3), 1.0)
    
    # Consistency score (how often these tools appear together)
    consistency_score = frequency / total_sequences if total_sequences > 0 else 0
    
    # Recency score (favor recent patterns)
    if pattern_data["last_seen"]:
        days_ago = (datetime.utcnow() - pattern_data["last_seen"]).days
        recency_score = max(0, 1 - (days_ago / ANALYSIS_WINDOW_DAYS))
    else:
        recency_score = 0.5
    
    # Weighted average
    confidence = (
        frequency_score * 0.4 +
        consistency_score * 0.4 +
        recency_score * 0.2
    )
    
    return min(confidence, 1.0)


def _infer_data_flow(occurrences: list) -> list:
    """
    Infer data flow between tools by analyzing how data moves between steps
    
    Args:
        occurrences: List of sequence documents
    
    Returns:
        List of data flow mappings
    """
    data_flow = []
    flow_counts = defaultdict(int)
    
    try:
        for occurrence in occurrences:
            sequence = occurrence.get("sequence", [])
            
            if len(sequence) < 2:
                continue
            
            # Analyze each step transition
            for i in range(1, len(sequence)):
                current_step = sequence[i]
                current_args = current_step.get("args", {})
                
                # Check if any arg values match previous outputs
                for j in range(i):
                    previous_step = sequence[j]
                    previous_output = previous_step.get("output", {})
                    
                    if not isinstance(previous_output, dict):
                        continue
                    
                    # Find matching values
                    matches = _find_value_matches(current_args, previous_output)
                    
                    for arg_key, output_path in matches:
                        flow_key = f"step{j}.{output_path}→step{i}.{arg_key}"
                        flow_counts[flow_key] += 1
        
        # Convert to structured format
        total_occurrences = len(occurrences)
        min_occurrence_ratio = 0.5  # Must occur in at least 50% of cases
        
        for flow_key, count in flow_counts.items():
            if count / total_occurrences >= min_occurrence_ratio:
                # Parse flow_key
                parts = flow_key.split("→")
                if len(parts) == 2:
                    from_part = parts[0].split(".")
                    to_part = parts[1].split(".")
                    
                    if len(from_part) >= 2 and len(to_part) >= 2:
                        data_flow.append({
                            "from_step": int(from_part[0].replace("step", "")),
                            "from_field": ".".join(from_part[1:]),
                            "to_step": int(to_part[0].replace("step", "")),
                            "to_arg": ".".join(to_part[1:]),
                            "confidence": count / total_occurrences
                        })
        
    except Exception as error:
        logger.error(f"Error inferring data flow: {error}")
    
    return data_flow


def _find_value_matches(args: dict, output: dict, prefix: str = "") -> list:
    """
    Find values in args that match values in output
    
    Returns:
        List of (arg_key, output_path) tuples
    """
    matches = []
    
    for arg_key, arg_value in args.items():
        if arg_value is None or arg_value == "":
            continue
        
        # Search for this value in output
        output_paths = _find_value_in_dict(output, arg_value)
        
        for path in output_paths:
            matches.append((arg_key, path))
    
    return matches


def _find_value_in_dict(data: dict, target_value: Any, current_path: str = "") -> list:
    """
    Recursively find paths to a value in a nested dictionary
    
    Returns:
        List of dot-separated paths where value was found
    """
    paths = []
    
    if not isinstance(data, dict):
        return paths
    
    for key, value in data.items():
        path = f"{current_path}.{key}" if current_path else key
        
        if value == target_value:
            paths.append(path)
        elif isinstance(value, dict):
            paths.extend(_find_value_in_dict(value, target_value, path))
    
    return paths


async def analyze_sequences(org_id: str, bridge_id: str) -> dict:
    """
    Analyze tool sequences and return insights
    
    Returns:
        Dictionary with analysis results
    """
    try:
        # Get recent sequences
        cutoff_date = datetime.utcnow() - timedelta(days=ANALYSIS_WINDOW_DAYS)
        
        sequences = await tool_execution_sequences_collection.find({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "timestamp": {"$gte": cutoff_date}
        }).to_list(length=None)
        
        if not sequences:
            return {
                "total_sequences": 0,
                "patterns_detected": 0,
                "recommendations": []
            }
        
        # Analyze
        pattern_data = _analyze_sequences_for_patterns(sequences)
        
        # Get existing learned patterns
        existing_patterns = await learned_tool_patterns_collection.find({
            "org_id": org_id,
            "bridge_id": bridge_id
        }).to_list(length=None)
        
        # Generate recommendations
        recommendations = []
        for pattern_hash, data in pattern_data.items():
            if data["frequency"] >= MIN_PATTERN_OCCURRENCES:
                confidence = _calculate_confidence(data, sequences)
                
                if confidence >= MIN_CONFIDENCE:
                    # Check if already exists
                    existing = any(p["pattern_hash"] == pattern_hash for p in existing_patterns)
                    
                    if not existing:
                        recommendations.append({
                            "tools": data["tool_names"],
                            "frequency": data["frequency"],
                            "confidence": confidence,
                            "potential_savings_ms": 4000,  # 2 AI calls * ~2s each
                            "recommendation": "Create optimized chain"
                        })
        
        return {
            "total_sequences": len(sequences),
            "unique_patterns": len(pattern_data),
            "patterns_detected": len(existing_patterns),
            "recommendations": recommendations
        }
        
    except Exception as error:
        logger.error(f"Error analyzing sequences: {error}")
        return {
            "total_sequences": 0,
            "patterns_detected": 0,
            "recommendations": []
        }
