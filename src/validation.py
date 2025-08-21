"""
Validation engine for Xero Payroll Automation system.

This module contains validation classes for ensuring data integrity
before processing payroll data and interacting with Xero APIs.
"""

from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional, Any
from enum import Enum
from config.settings import FUZZY_MATCH_THRESHOLD, FUZZY_MATCH_CUTOFF
from rapidfuzz import fuzz


class ValidationStatus(Enum):
    """Status of validation operations."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    WARNING = "WARNING"


class MatchConfidence(Enum):
    """Confidence levels for fuzzy matching."""
    HIGH = "HIGH"      # 90%+ match
    MEDIUM = "MEDIUM"  # 70-89% match
    LOW = "LOW"        # 50-69% match
    NO_MATCH = "NO_MATCH"  # <50% match


@dataclass
class ValidationError:
    """Represents a single validation error."""
    error_type: str
    message: str
    field_name: Optional[str] = None
    suggested_fix: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation of the validation error."""
        if self.field_name:
            return f"{self.error_type} in {self.field_name}: {self.message}"
        return f"{self.error_type}: {self.message}"


@dataclass
class ValidationResult:
    """
    Result of a validation operation.
    
    Contains the validation status, any errors found, and additional
    metadata about the validation process.
    """
    status: ValidationStatus
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    validated_items: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_valid(self) -> bool:
        """Check if validation passed without errors."""
        return self.status == ValidationStatus.SUCCESS and len(self.errors) == 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if validation has warnings."""
        return len(self.warnings) > 0
    
    def add_error(self, error_type: str, message: str, field_name: Optional[str] = None, 
                  suggested_fix: Optional[str] = None) -> None:
        """Add a validation error."""
        self.errors.append(ValidationError(error_type, message, field_name, suggested_fix))
        if self.status == ValidationStatus.SUCCESS:
            self.status = ValidationStatus.FAILED
    
    def add_warning(self, error_type: str, message: str, field_name: Optional[str] = None,
                   suggested_fix: Optional[str] = None) -> None:
        """Add a validation warning."""
        self.warnings.append(ValidationError(error_type, message, field_name, suggested_fix))
        if self.status == ValidationStatus.SUCCESS:
            self.status = ValidationStatus.WARNING
    
    def get_error_summary(self) -> str:
        """Get a formatted summary of all errors and warnings."""
        lines = []
        
        if self.errors:
            lines.append("❌ Validation Errors:")
            for error in self.errors:
                lines.append(f"   - {error}")
                if error.suggested_fix:
                    lines.append(f"     Action: {error.suggested_fix}")
        
        if self.warnings:
            lines.append("⚠️  Validation Warnings:")
            for warning in self.warnings:
                lines.append(f"   - {warning}")
                if warning.suggested_fix:
                    lines.append(f"     Suggestion: {warning.suggested_fix}")
        
        if not lines:
            lines.append("✅ Validation passed successfully")
        
        return "\n".join(lines)


@dataclass
class MatchResult:
    """
    Result of an employee name matching operation.
    
    Contains information about potential matches and confidence levels
    for fuzzy string matching operations.
    """
    input_name: str
    matched_name: Optional[str] = None
    matched_id: Optional[str] = None
    confidence: MatchConfidence = MatchConfidence.NO_MATCH
    confidence_score: float = 0.0
    suggestions: List[Dict[str, Any]] = field(default_factory=list)
    requires_confirmation: bool = True
    
    @property
    def is_automatic_match(self) -> bool:
        """Check if match confidence is high enough for automatic processing."""
        return self.confidence == MatchConfidence.HIGH and not self.requires_confirmation
    
    @property
    def has_suggestions(self) -> bool:
        """Check if there are suggested matches available."""
        return len(self.suggestions) > 0
    
    def add_suggestion(self, name: str, employee_id: str, score: float) -> None:
        """Add a suggested match."""
        self.suggestions.append({
            "name": name,
            "employee_id": employee_id,
            "score": score
        })


class RegionValidator:
    """
    Validates region names against Xero tracking categories.
    
    This class performs strict validation of region names to ensure
    they exactly match regions configured in Xero before processing
    timesheet data.
    """
    
    def __init__(self, xero_regions: Optional[List[str]] = None):
        """
        Initialize the RegionValidator.
        
        Args:
            xero_regions: List of valid region names from Xero tracking categories
        """
        self.xero_regions = set(xero_regions) if xero_regions else set()
        self._region_cache = {}
    
    def set_xero_regions(self, xero_regions: List[str]) -> None:
        """
        Set the list of valid Xero regions.
        
        Args:
            xero_regions: List of valid region names from Xero tracking categories
        """
        self.xero_regions = set(xero_regions)
        self._region_cache.clear()
    
    def validate_region(self, region_name: str) -> ValidationResult:
        """
        Validate a single region name against Xero tracking categories.
        
        Args:
            region_name: Region name to validate
            
        Returns:
            ValidationResult indicating if the region is valid
        """
        result = ValidationResult(status=ValidationStatus.SUCCESS, validated_items=1)
        
        if not region_name or not region_name.strip():
            result.add_error(
                "EMPTY_REGION",
                "Region name cannot be empty",
                "region_name",
                "Ensure all timesheet entries have valid region names"
            )
            return result
        
        region_name = region_name.strip()
        
        # Check cache first
        if region_name in self._region_cache:
            if not self._region_cache[region_name]:
                result.add_error(
                    "INVALID_REGION",
                    f"Region '{region_name}' not found in Xero tracking categories",
                    "region_name",
                    f"Add '{region_name}' region in Xero UI under Payroll Settings > Timesheets > Categories"
                )
            return result
        
        # Validate against Xero regions
        if not self.xero_regions:
            result.add_error(
                "NO_XERO_REGIONS",
                "No Xero regions available for validation",
                "xero_regions",
                "Ensure Xero API connection is established and regions are fetched"
            )
            return result
        
        is_valid = region_name in self.xero_regions
        self._region_cache[region_name] = is_valid
        
        if not is_valid:
            # Find similar region names for suggestions
            suggestions = self._find_similar_regions(region_name)
            suggestion_text = f"Add '{region_name}' region in Xero UI under Payroll Settings > Timesheets > Categories"
            
            if suggestions:
                suggestion_text += f". Did you mean: {', '.join(suggestions[:3])}?"
            
            result.add_error(
                "INVALID_REGION",
                f"Region '{region_name}' not found in Xero tracking categories",
                "region_name",
                suggestion_text
            )
        
        return result
    
    def validate_regions(self, regions: Set[str]) -> ValidationResult:
        """
        Validate multiple region names against Xero tracking categories.
        
        Args:
            regions: Set of region names to validate
            
        Returns:
            ValidationResult with all validation errors
        """
        result = ValidationResult(status=ValidationStatus.SUCCESS, validated_items=len(regions))
        
        if not regions:
            result.add_warning(
                "NO_REGIONS",
                "No regions found to validate",
                "regions",
                "Ensure timesheet data contains region information"
            )
            return result
        
        invalid_regions = []
        
        for region_name in sorted(regions):
            region_result = self.validate_region(region_name)
            
            # Merge errors and warnings
            result.errors.extend(region_result.errors)
            result.warnings.extend(region_result.warnings)
            
            if not region_result.is_valid:
                invalid_regions.append(region_name)
        
        # Update overall status
        if result.errors:
            result.status = ValidationStatus.FAILED
        elif result.warnings:
            result.status = ValidationStatus.WARNING
        
        # Add metadata
        result.metadata.update({
            "total_regions": len(regions),
            "valid_regions": len(regions) - len(invalid_regions),
            "invalid_regions": invalid_regions,
            "xero_regions_count": len(self.xero_regions)
        })
        
        return result
    
    def _find_similar_regions(self, region_name: str, threshold: float = 60.0) -> List[str]:
        """
        Find similar region names using fuzzy matching.
        
        Args:
            region_name: Region name to find matches for
            threshold: Minimum similarity score (0-100)
            
        Returns:
            List of similar region names sorted by similarity
        """
        if not self.xero_regions:
            return []
        
        matches = []
        for xero_region in self.xero_regions:
            score = fuzz.ratio(region_name.lower(), xero_region.lower())
            if score >= threshold:
                matches.append((xero_region, score))
        
        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return [match[0] for match in matches]
    
    def get_validation_summary(self, regions: Set[str]) -> str:
        """
        Get a formatted summary of region validation.
        
        Args:
            regions: Set of regions to validate
            
        Returns:
            Formatted validation summary string
        """
        result = self.validate_regions(regions)
        return result.get_error_summary()


class EmployeeMatcher:
    """
    Matches employee names using fuzzy string matching.
    
    This class handles employee name variations by using fuzzy matching
    algorithms to suggest potential matches and handle user confirmation
    for ambiguous cases.
    """
    
    def __init__(self, xero_employees: Optional[List[Dict[str, Any]]] = None,
             auto_match_threshold: float = FUZZY_MATCH_THRESHOLD, suggestion_threshold: float = FUZZY_MATCH_CUTOFF):
        """
        Initialize the EmployeeMatcher.
        
        Args:
            xero_employees: List of employee dictionaries from Xero API
            auto_match_threshold: Minimum score for automatic matching (0-100)
            suggestion_threshold: Minimum score for suggesting matches (0-100)
        """
        self.xero_employees = xero_employees or []
        self.auto_match_threshold = auto_match_threshold
        self.suggestion_threshold = suggestion_threshold
        self._match_cache = {}
        
        # Create lookup dictionaries for efficient matching
        self._employee_lookup = {}
        self._name_variations = {}
        self._build_lookup_tables()
    
    def set_xero_employees(self, xero_employees: List[Dict[str, Any]]) -> None:
        """
        Set the list of Xero employees.
        
        Args:
            xero_employees: List of employee dictionaries from Xero API
                          Expected format: [{"employee_id": "uuid", "name": "Full Name"}, ...]
        """
        self.xero_employees = xero_employees
        self._match_cache.clear()
        self._build_lookup_tables()
    
    def _build_lookup_tables(self) -> None:
        """Build internal lookup tables for efficient matching."""
        self._employee_lookup.clear()
        self._name_variations.clear()
        
        for employee in self.xero_employees:
            employee_id = employee.get("employee_id")
            name = employee.get("name", "").strip()
            
            if not employee_id or not name:
                continue
            
            # Store by full name
            self._employee_lookup[name] = employee
            
            # Create name variations for better matching
            variations = self._generate_name_variations(name)
            for variation in variations:
                if variation not in self._name_variations:
                    self._name_variations[variation] = []
                self._name_variations[variation].append(employee)
    
    def _generate_name_variations(self, full_name: str) -> List[str]:
        """
        Generate common name variations for better matching.
        
        Args:
            full_name: Full employee name
            
        Returns:
            List of name variations
        """
        variations = [full_name]
        
        # Split name into parts
        parts = full_name.split()
        if len(parts) < 2:
            return variations
        
        # Add first name + last name initial (e.g., "John S.")
        if len(parts) >= 2:
            first_last_initial = f"{parts[0]} {parts[-1][0]}."
            variations.append(first_last_initial)
        
        # Add first initial + last name (e.g., "J. Smith")
        if len(parts) >= 2:
            first_initial_last = f"{parts[0][0]}. {parts[-1]}"
            variations.append(first_initial_last)
        
        # Add first initial + middle initial + last name (e.g., "J. M. Smith")
        if len(parts) >= 3:
            initials = [part[0] + "." for part in parts[:-1]]
            initials_last = " ".join(initials) + " " + parts[-1]
            variations.append(initials_last)
        
        # Add last name, first name format
        if len(parts) >= 2:
            last_first = f"{parts[-1]}, {parts[0]}"
            variations.append(last_first)
        
        return variations
    
    def match_employee(self, timesheet_name: str, require_confirmation: bool = True) -> MatchResult:
        """
        Match an employee name from timesheet data to Xero employees.
        
        Args:
            timesheet_name: Employee name from timesheet
            require_confirmation: Whether to require user confirmation for matches
            
        Returns:
            MatchResult with match information and suggestions
        """
        if not timesheet_name or not timesheet_name.strip():
            return MatchResult(
                input_name=timesheet_name,
                confidence=MatchConfidence.NO_MATCH,
                requires_confirmation=True
            )
        
        timesheet_name = timesheet_name.strip()
        
        # Check cache first
        cache_key = (timesheet_name, require_confirmation)
        if cache_key in self._match_cache:
            return self._match_cache[cache_key]
        
        # Try exact match first
        exact_match = self._find_exact_match(timesheet_name)
        if exact_match:
            result = MatchResult(
                input_name=timesheet_name,
                matched_name=exact_match["name"],
                matched_id=exact_match["employee_id"],
                confidence=MatchConfidence.HIGH,
                confidence_score=100.0,
                requires_confirmation=False
            )
            self._match_cache[cache_key] = result
            return result
        
        # Try fuzzy matching
        fuzzy_matches = self._find_fuzzy_matches(timesheet_name)
        
        if not fuzzy_matches:
            result = MatchResult(
                input_name=timesheet_name,
                confidence=MatchConfidence.NO_MATCH,
                requires_confirmation=True
            )
            self._match_cache[cache_key] = result
            return result
        
        # Get best match
        best_match = fuzzy_matches[0]
        confidence_score = best_match["score"]
        
        # Determine confidence level
        if confidence_score >= self.auto_match_threshold:
            confidence = MatchConfidence.HIGH
            requires_confirmation = require_confirmation
        elif confidence_score >= 70.0:
            confidence = MatchConfidence.MEDIUM
            requires_confirmation = True
        elif confidence_score >= 50.0:
            confidence = MatchConfidence.LOW
            requires_confirmation = True
        else:
            confidence = MatchConfidence.NO_MATCH
            requires_confirmation = True
        
        result = MatchResult(
            input_name=timesheet_name,
            matched_name=best_match["name"] if confidence != MatchConfidence.NO_MATCH else None,
            matched_id=best_match["employee_id"] if confidence != MatchConfidence.NO_MATCH else None,
            confidence=confidence,
            confidence_score=confidence_score,
            requires_confirmation=requires_confirmation
        )
        
        # Add suggestions (top 5 matches above suggestion threshold)
        for match in fuzzy_matches[:5]:
            if match["score"] >= self.suggestion_threshold:
                result.add_suggestion(
                    match["name"],
                    match["employee_id"],
                    match["score"]
                )
        
        self._match_cache[cache_key] = result
        return result
    
    def _find_exact_match(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find exact match for employee name.
        
        Args:
            name: Employee name to match
            
        Returns:
            Employee dictionary if exact match found, None otherwise
        """
        # Try direct lookup
        if name in self._employee_lookup:
            return self._employee_lookup[name]
        
        # Try case-insensitive lookup
        for employee_name, employee in self._employee_lookup.items():
            if employee_name.lower() == name.lower():
                return employee
        
        return None
    
    def _find_fuzzy_matches(self, name: str) -> List[Dict[str, Any]]:
        """
        Find fuzzy matches for employee name.
        
        Args:
            name: Employee name to match
            
        Returns:
            List of matches sorted by score (highest first)
        """
        matches = []

        # Normalize input name
        name_norm = name.lower().strip()
        name_parts = name_norm.split()
        input_last = name_parts[-1] if len(name_parts) >= 2 else ""

        for employee in self.xero_employees:
            employee_name = employee.get("name", "")
            employee_id = employee.get("employee_id", "")

            # Skip employees with missing required fields
            if not employee_name or not employee_id:
                continue

            emp_name_norm = employee_name.lower().strip()

            # Calculate similarity scores using different algorithms
            ratio_score = fuzz.ratio(name_norm, emp_name_norm)
            partial_score = fuzz.partial_ratio(name_norm, emp_name_norm)
            token_sort_score = fuzz.token_sort_ratio(name_norm, emp_name_norm)
            token_set_score = fuzz.token_set_ratio(name_norm, emp_name_norm)

            # Use the highest score as primary similarity metric
            best_score = max(ratio_score, partial_score, token_sort_score, token_set_score)

            # Additional safeguard: compare last names (if both present) to avoid false positives
            emp_parts = emp_name_norm.split()
            emp_last = emp_parts[-1] if len(emp_parts) >= 2 else ""
            last_name_score = 0
            if input_last and emp_last:
                last_name_score = fuzz.ratio(input_last, emp_last)

            # Heuristic: accept candidate only if primary score passes threshold AND
            # either last names are reasonably similar or token-based scores are strong
            token_based_strong = (token_set_score >= self.suggestion_threshold or token_sort_score >= self.suggestion_threshold)
            last_name_similar = last_name_score >= 60  # require stronger last-name similarity

            if best_score >= self.suggestion_threshold and (token_based_strong or last_name_similar):
                matches.append({
                    "name": employee_name,
                    "employee_id": employee_id,
                    "score": best_score,
                    "last_name_score": last_name_score
                })

        # Sort by score descending
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches
    
    def match_employees_batch(self, timesheet_names: List[str], 
                            require_confirmation: bool = True) -> Dict[str, MatchResult]:
        """
        Match multiple employee names in batch.
        
        Args:
            timesheet_names: List of employee names from timesheet
            require_confirmation: Whether to require user confirmation for matches
            
        Returns:
            Dictionary mapping timesheet names to MatchResult objects
        """
        results = {}
        
        for name in timesheet_names:
            results[name] = self.match_employee(name, require_confirmation)
        
        return results
    
    def get_unmatched_employees(self, timesheet_names: List[str]) -> List[str]:
        """
        Get list of employee names that couldn't be matched.
        
        Args:
            timesheet_names: List of employee names from timesheet
            
        Returns:
            List of unmatched employee names
        """
        unmatched = []
        
        for name in timesheet_names:
            result = self.match_employee(name, require_confirmation=False)
            if result.confidence == MatchConfidence.NO_MATCH:
                unmatched.append(name)
        
        return unmatched
    
    def get_ambiguous_matches(self, timesheet_names: List[str]) -> List[MatchResult]:
        """
        Get list of matches that require user confirmation.
        
        Args:
            timesheet_names: List of employee names from timesheet
            
        Returns:
            List of MatchResult objects requiring confirmation
        """
        ambiguous = []
        
        for name in timesheet_names:
            result = self.match_employee(name, require_confirmation=True)
            if result.requires_confirmation and result.has_suggestions:
                ambiguous.append(result)
        
        return ambiguous
    
    def confirm_match(self, timesheet_name: str, confirmed_employee_id: str) -> bool:
        """
        Confirm a match for an employee name.
        
        Args:
            timesheet_name: Original timesheet name
            confirmed_employee_id: Confirmed Xero employee ID
            
        Returns:
            True if confirmation was successful, False otherwise
        """
        # Find the employee by ID
        confirmed_employee = None
        for employee in self.xero_employees:
            if employee.get("employee_id") == confirmed_employee_id:
                confirmed_employee = employee
                break
        
        if not confirmed_employee:
            return False
        
        # Update cache with confirmed match
        cache_key = (timesheet_name, True)
        confirmed_result = MatchResult(
            input_name=timesheet_name,
            matched_name=confirmed_employee["name"],
            matched_id=confirmed_employee_id,
            confidence=MatchConfidence.HIGH,
            confidence_score=100.0,
            requires_confirmation=False
        )
        
        self._match_cache[cache_key] = confirmed_result
        return True
    
    def get_matching_statistics(self, timesheet_names: List[str]) -> Dict[str, Any]:
        """
        Get statistics about employee matching results.
        
        Args:
            timesheet_names: List of employee names from timesheet
            
        Returns:
            Dictionary with matching statistics
        """
        if not timesheet_names:
            return {
                "total_employees": 0,
                "exact_matches": 0,
                "fuzzy_matches": 0,
                "no_matches": 0,
                "requires_confirmation": 0,
                "match_rate": 0.0
            }
        
        exact_matches = 0
        fuzzy_matches = 0
        no_matches = 0
        requires_confirmation = 0
        
        for name in timesheet_names:
            result = self.match_employee(name, require_confirmation=True)
            
            if result.confidence_score == 100.0:
                exact_matches += 1
            elif result.confidence != MatchConfidence.NO_MATCH:
                fuzzy_matches += 1
            else:
                no_matches += 1
            
            if result.requires_confirmation:
                requires_confirmation += 1
        
        total = len(timesheet_names)
        matched = exact_matches + fuzzy_matches
        
        return {
            "total_employees": total,
            "exact_matches": exact_matches,
            "fuzzy_matches": fuzzy_matches,
            "no_matches": no_matches,
            "requires_confirmation": requires_confirmation,
            "match_rate": (matched / total) * 100.0 if total > 0 else 0.0
        }