from typing import List, Dict, Tuple, Optional, Any
import re
import logging

class QueryClassifier:
    """
    Classifies queries to determine whether to use document retrieval,
    web search, or a hybrid approach.
    """
    
    def __init__(self, confidence_threshold: float = 0.6):
        """
        Initialize the classifier with default settings.
        
        Args:
            confidence_threshold: Threshold for classification decisions (0-1)
        """
        self.confidence_threshold = confidence_threshold
        self.logger = logging.getLogger(__name__)
        
        # Initialize with default product terms
        self.product_terms = ["duplocloud", "tenant", "infrastructure"]
            
    def update_terms_from_db(self, db_collection, ollama_client):
        """
        Update product terms using content stored in ChromaDB with
        Ollama-powered entity extraction
        
        Args:
            db_collection: ChromaDB collection containing document embeddings
            ollama_client: OllamaClient instance for LLM-powered entity extraction
        """
        try:
            # Get all documents from the collection
            all_docs = db_collection.get(include=["documents"])
            if not all_docs or "documents" not in all_docs or not all_docs["documents"]:
                self.logger.warning("No documents found in ChromaDB for term extraction")
                return
                
            self.logger.info("Using Ollama for intelligent domain term extraction")
            # Use a sample of documents (to avoid context length issues)
            doc_sample = self._sample_documents(all_docs["documents"])
            extracted_terms = self._extract_terms_with_ollama(doc_sample, ollama_client)
            
            # Fall back to minimal terms if extraction fails
            if not extracted_terms:
                self.logger.warning("LLM term extraction failed, falling back to minimal terms")
                extracted_terms = ["duplocloud", "tenant", "infrastructure"]
            
            # Set the product terms to the extracted terms
            self.product_terms = extracted_terms
            
            self.logger.info(f"Updated product terms from ChromaDB: Found {len(self.product_terms)} terms")
            
        except Exception as e:
            self.logger.error(f"Error extracting terms from ChromaDB: {e}")
            # Fall back to minimal terms
            self.product_terms = ["duplocloud", "tenant", "infrastructure"]
    
    def _sample_documents(self, documents, max_docs=50, max_chars=10000):
        """
        Sample a subset of documents to avoid context length issues
        """
        if len(documents) <= max_docs:
            # Take all documents if we have fewer than max_docs
            sample_docs = documents
        else:
            # Sample documents, prioritizing shorter ones
            # Sort by length and take the first max_docs
            sorted_docs = sorted(documents, key=len)
            sample_docs = sorted_docs[:max_docs]
        
        # Truncate the combined text if it's too long
        combined_text = "\n\n".join(sample_docs)
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars]
            
        return combined_text
            
    def _extract_terms_with_ollama(self, text, ollama_client, max_terms=100):
        """
        Use Ollama LLM to extract domain-specific terms, entities, subjects, etc.
        
        Args:
            text: The text to analyze
            ollama_client: OllamaClient instance
            max_terms: Maximum number of terms to return
            
        Returns:
            List of domain-specific terms extracted by the LLM
        """
        prompt = f"""You are an expert at extracting domain-specific terminology and entities from text.

I'll provide you with text from a knowledge base, and I need you to identify important domain-specific terms, entities, and concepts that would be valuable for information retrieval.

Extract the following types of terms:
1. Technical terms and jargon specific to this domain
2. Product names, features, and components
3. Proper nouns (people, organizations, places)
4. Domain-specific concepts 
5. Important actions or processes
6. Abbreviations and acronyms with their expansions

You MUST follow these formatting instructions exactly:
- Your response must consist ONLY of a valid JSON array of strings
- Begin your response with [ and end with ]
- Each extracted term should be a string inside the array
- Include both single words and multi-word phrases (2-3 word phrases)
- Make sure to escape any special characters properly
- Do not add any commentary, explanation, or markdown formatting
- Do not include the term "json" or "array" in your response
- Format must be parseable by JSON.parse()

Example correct response format:
["term1", "term2", "concept name", "technical jargon", "organization name"]

Here is the text to analyze:

```
{text}
```
"""

        try:
            # Generate response from Ollama
            response = ollama_client.generate_response(context="", query=prompt)
            
            # Log the raw response for debugging
            self.logger.debug(f"Raw Ollama response: {response[:200]}...")
            
            # Extract JSON array from response using multiple approaches
            import re
            import json
            
            # Approach 1: Clean up response and attempt to parse
            # Remove any markdown code block markers
            cleaned_response = re.sub(r'```json|```|\s*```', '', response)
            # Remove any non-array text before or after the array
            cleaned_response = re.sub(r'^[^[]*', '', cleaned_response)
            cleaned_response = re.sub(r'[^\]]*$', '', cleaned_response)
            
            # Try to parse the cleaned response
            try:
                terms = json.loads(cleaned_response)
                
                # Ensure we have a list of strings
                if isinstance(terms, list):
                    # Filter to ensure all terms are strings
                    terms = [str(term).strip().lower() for term in terms if term]
                    
                    # Deduplicate
                    terms = list(dict.fromkeys(terms))
                    
                    # Limit to max_terms
                    terms = terms[:max_terms]
                    
                    self.logger.info(f"Successfully extracted {len(terms)} terms using Ollama")
                    return terms
                else:
                    self.logger.warning(f"Ollama returned invalid terms format: {type(terms)}")
            except json.JSONDecodeError:
                self.logger.warning("Could not parse cleaned JSON response")
            
            # Approach 2: Look for an array pattern with regex
            json_match = re.search(r'\[(.*?)\]', response, re.DOTALL)
            if json_match:
                try:
                    json_str = json_match.group(0)
                    terms = json.loads(json_str)
                    
                    # Ensure we have a list of strings
                    if isinstance(terms, list):
                        # Filter to ensure all terms are strings
                        terms = [str(term).strip().lower() for term in terms if term]
                        
                        # Deduplicate
                        terms = list(dict.fromkeys(terms))
                        
                        # Limit to max_terms
                        terms = terms[:max_terms]
                        
                        self.logger.info(f"Successfully extracted {len(terms)} terms using regex approach")
                        return terms
                except json.JSONDecodeError:
                    self.logger.warning("Could not parse JSON from regex match")
            
            # Approach 3: Extract terms manually with regex if JSON parsing fails
            self.logger.warning("Falling back to manual term extraction with regex")
            # Look for quoted strings that might be terms
            quoted_terms = re.findall(r'"([^"]+)"', response)
            if quoted_terms:
                # Process quoted terms
                terms = [term.strip().lower() for term in quoted_terms if term.strip()]
                
                # Deduplicate
                terms = list(dict.fromkeys(terms))
                
                # Limit to max_terms
                terms = terms[:max_terms]
                
                self.logger.info(f"Extracted {len(terms)} terms using quoted string approach")
                return terms
                
            # If all else fails, extract potential terms with basic pattern matching
            self.logger.warning("Falling back to line-by-line extraction")
            potential_terms = []
            
            # Split response by lines and look for patterns like "- term" or "* term" or numbered lists
            lines = response.split('\n')
            for line in lines:
                # Remove markdown list markers and other formatting
                line = re.sub(r'^[-*•]|\d+[.)]|\s+', ' ', line).strip()
                
                # Skip empty lines or very long lines
                if not line or len(line) > 100:
                    continue
                    
                # Remove any quotes
                line = line.replace('"', '').replace("'", "")
                
                # Add cleaned line as a potential term
                if line:
                    potential_terms.append(line.lower())
            
            if potential_terms:
                # Deduplicate
                terms = list(dict.fromkeys(potential_terms))
                
                # Limit to max_terms
                terms = terms[:max_terms]
                
                self.logger.info(f"Extracted {len(terms)} terms using line approach")
                return terms
            
            self.logger.warning("All term extraction methods failed")
            return []
                
        except Exception as e:
            self.logger.error(f"Error using Ollama for term extraction: {e}")
            return []
    
    def classify(self, 
                query: str, 
                doc_scores: Optional[List[float]] = None) -> Tuple[str, float, Dict[str, Any]]:
        """
        Classify a query to determine the best source for answering.
        
        Args:
            query: The user's query text
            doc_scores: Relevance scores for retrieved documents (if available)
            
        Returns:
            Tuple containing:
            - source_type: "documents", "web", or "hybrid"
            - confidence: confidence score (0-1)
            - metadata: Additional classification data
        """
        scores = {
            "documents": 0.0,
            "web": 0.0
        }
        explanations = []
        
        # Check for DuploCloud-specific terminology
        term_score, term_matches = self._keyword_match(query)
        scores["documents"] = term_score
        explanations.append(f"Term match: {term_score:.2f} (found {len(term_matches)} DuploCloud terms)")
        
        # If document scores are provided, factor them in
        retrieval_score = 0.0
        if doc_scores and len(doc_scores) > 0:
            retrieval_score = min(1.0, max(doc_scores))
            scores["documents"] = 0.7 * scores["documents"] + 0.3 * retrieval_score
            explanations.append(f"Document relevance: {retrieval_score:.2f}")
        
        # Calculate web score (inverse of document score)
        scores["web"] = 1.0 - scores["documents"]
        
        # Determine if hybrid approach is better
        # If document score is in the middle range (0.3-0.7), hybrid might be best
        hybrid_score = 1.0 - 2.0 * abs(scores["documents"] - 0.5)
        scores["hybrid"] = max(0.0, hybrid_score)
        
        # Determine the source to use based on scores and thresholds
        if scores["documents"] >= self.confidence_threshold:
            source_type = "documents"
            confidence = scores["documents"]
        elif scores["web"] >= self.confidence_threshold:
            source_type = "web"
            confidence = scores["web"]
        else:
            source_type = "hybrid"
            confidence = scores["hybrid"]
        
        # Prepare metadata with explanation of decision
        metadata = {
            "scores": scores,
            "explanations": explanations,
            "matched_terms": term_matches
        }
        
        return source_type, confidence, metadata
    
    def _keyword_match(self, query: str) -> Tuple[float, List[str]]:
        """
        Check for DuploCloud-specific terms in the query.
        
        Args:
            query: The query text to analyze
            
        Returns:
            Tuple containing:
            - score: Confidence score for document retrieval (0-1)
            - matches: List of matched product terms
        """
        query_lower = query.lower()
        matches = []
        
        # Find matching product terms in the query
        for term in self.product_terms:
            # Use word boundary to find whole word matches
            if re.search(r'\b' + re.escape(term.lower()) + r'\b', query_lower):
                matches.append(term)
        
        # Calculate score based on number of matches
        if not matches:
            return 0.0, []
        
        # Score increases with more matches but caps at 1.0
        # A single match gives 0.4, two matches 0.7, three or more 0.9+
        score = min(1.0, 0.4 + (len(matches) - 1) * 0.3)
        return score, matches
