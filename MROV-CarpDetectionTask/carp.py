#!/usr/bin/env python
"""
Detect Carp Species from an eDNA sequence.

This script uses Biopython’s pairwise2 module to locally align an input 
query sequence to one of four carp species reference sequences:
- Bighead Carp
- Silver Carp
- Grass Carp
- Black Carp

It then selects the species with the highest percent identity (if above a threshold).

Before running, install Biopython with:
    pip install biopython
"""

from Bio import pairwise2
from Bio.Seq import Seq

import os, argparse, cv2, pytesseract, re
from PIL import Image
from pdf2image import convert_from_path
import tempfile

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Define reference sequences for each carp species (example sequences).
# These sequences are derived from available eDNA records.
# In practice, adjust these sequences to match your full reference data.

def preprocess(img_path):
    #read image and conv to grayscale
    img=cv2.imread(img_path)
    grey=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    _,thresh=cv2.threshold(grey,150,255,cv2.THRESH_BINARY)

    proc=cv2.medianBlur(thresh,3)

    return proc

def extract_dna(file_path):
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.pdf':
        return extract_dna_from_pdf(file_path)
    elif file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        return extract_dna_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}")


def extract_dna_from_pdf(pdf_path):
    """
    Extract DNA sequences from a PDF file using OCR.
    Converts PDF pages to images and processes each page.
    Returns a dictionary with sample numbers as keys and sequences as values.
    """
    try:
        # Convert PDF pages to images
        pages = convert_from_path(pdf_path, dpi=300)
        
        all_sequences = {}
        current_sample = None
        
        for i, page in enumerate(pages):
            print(f"Processing page {i+1} of {len(pages)}...")
            
            # Save page as temporary image
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                page.save(temp_file.name, 'PNG')
                temp_path = temp_file.name
            
            try:
                # Extract both text and DNA from this page
                page_sequences = extract_sequences_from_image(temp_path)
                
                # Merge sequences from this page
                for sample_id, sequence in page_sequences.items():
                    if sample_id in all_sequences:
                        all_sequences[sample_id] += sequence
                    else:
                        all_sequences[sample_id] = sequence
                    print(f"Page {i+1}, Sample {sample_id}: Found {len(sequence)} DNA characters")
                        
            finally:
                # Clean up temporary file
                os.unlink(temp_path)
        
        # Print summary
        for sample_id, sequence in all_sequences.items():
            print(f"Sample {sample_id}: Total length {len(sequence)} characters")
        
        return all_sequences
        
    except Exception as e:
        print(f"Error processing PDF: {e}")
        return {}

def extract_sequences_from_image(img_path):
    """
    Extract DNA sequences from an image, identifying separate samples.
    Returns a dictionary with sample IDs as keys and DNA sequences as values.
    """
    # Preprocess image
    processed_img = preprocess(img_path)
    
    # Extract full text first
    text = pytesseract.image_to_string(processed_img, config='--psm 3')
    
    # Split text into lines
    lines = text.split('\n')
    
    sequences = {}
    current_sample = None
    current_sequence = ""
    
    for line in lines:
        line = line.strip()
        
        # Check if this line contains a sample header
        sample_match = re.search(r'Unknown\s+Sample\s*\(?(\d+)\)?', line, re.IGNORECASE)
        if sample_match:
            # Save previous sequence if it exists
            if current_sample is not None and current_sequence:
                sequences[current_sample] = current_sequence
            
            # Start new sample
            current_sample = int(sample_match.group(1))
            current_sequence = ""
            print(f"Found sample header: Unknown Sample {current_sample}")
            continue
        
        # Extract DNA characters from this line
        dna_chars = re.findall(r'[ACGTacgt]', line)
        if dna_chars:
            dna_line = ''.join(dna_chars).upper()
            if current_sample is not None:
                current_sequence += dna_line
            else:
                # If no sample header found yet, use sample 1 as default
                if 1 not in sequences:
                    sequences[1] = ""
                    current_sample = 1
                current_sequence += dna_line
    
    # Don't forget the last sequence
    if current_sample is not None and current_sequence:
        sequences[current_sample] = current_sequence
    
    return sequences

def extract_dna_from_image(img_path):
    """
    Extract DNA sequence from an image file (single sequence version for backward compatibility).
    """
    sequences = extract_sequences_from_image(img_path)
    
    # Return the first sequence found, or combine all if multiple
    if len(sequences) == 1:
        return list(sequences.values())[0]
    elif len(sequences) > 1:
        print(f"Found {len(sequences)} sequences. Combining them.")
        return ''.join(sequences.values())
    else:
        return ""

def analyze_multiple_sequences(sequences_dict, ref_sequences, threshold=0.85):
    """
    Analyze multiple DNA sequences and return results for each.
    """
    results = {}
    
    for sample_id, sequence in sequences_dict.items():
        print(f"\n=== Analyzing Sample {sample_id} ===")
        print(f"Sequence length: {len(sequence)} characters")
        
        if len(sequence) < 50:  # Skip very short sequences
            print(f"Sample {sample_id}: Sequence too short for analysis")
            results[sample_id] = (None, 0.0, "Sequence too short")
            continue
        
        species, similarity = detect_carp_species(sequence, ref_sequences, threshold)
        
        if species:
            results[sample_id] = (species, similarity, "Match found")
            print(f"Sample {sample_id}: Detected {species} (Similarity: {similarity:.2%})")
        else:
            results[sample_id] = (None, similarity, "No match above threshold")
            print(f"Sample {sample_id}: No species detected above threshold. Best similarity: {similarity:.2%}")
    
    return results

ref_sequences = {
    "Bighead Carp": (
        "CTTCTGGTAGTACCTATATGGTTCAGTACATATTATGTATTATGTTACCTAATGTACTAATACCTATATATG"
        "TATTATCACCATTAATTTATTTTAACCTTAAAGCAAGTACTAACGTTTAAAAACGTACATAAACCAAAAT"
        "ATTAAGATTCATAAATAAATTATCTTAACTTAAATAAACAGATTATTCCACTAACAATTGATTCTCAAATT"
        "TATTACTGAATTATTAACTAAAATCTAACTCAAGTATATTATTAAAGTAAGAGACCACCTACTTATTTATA"
        "TTAAGGTATTATATTCATGATAAGATCAAGGACAATAACAGTGGGGGTGGCGCAAAATGAACTATTAC"
        "TTGCATCTGGTTTGGAATCTCACGGACATGGCTACAAAATTCCACCCCCGTTACATTATAACTGGCATA"
        "TGGTTAAATGATGTGAGTACATACTCCTCATTAACCCCACATGCCGAGCATTCTTTTATATGCATAGGG"
        "GTTCTCCTTTTGGTTTCCTTTCACCTTGCATATCAGAGTGCAAGCTCAAATAGTAAAATAAGGTTGAAC"
        "ATATTCCTTGCTTGTGTTAAAGTAAGTTAATTATTAAAAGACATAACTTAAGAATTACATATTTCTCACTC"
        "AAGTGCATAACATATTCATTCTTTCTTCAACTTACCCCTATATATATGCCCCCCCTTTTGGCTTCTGCGC"
        "GACAAACCCCCCTACCCCCTACGCTCAGCAAATCCTGTTATCCTTGTCAAACCCCAAAACCAAGGAA"
        "GGTTCGAGAACGTGCAAGCTAACAAGTTGAAATATGGGTTAGCTATCCGCATTATATATATATATATAC"
        "ATACACATCACATCAATTTACCACATAATTCCCCAAACATTGACCTAAAAACCCCTATTAAATTTATAGG"
        "ACATGCCCCAATGCTAAAAAGTCCAACATTATATAATGCTAG"
    ),
    "Silver Carp": (
        "TCTTCTGATATAACCTATATGGTTTAATACATATATGTATTATATTACATAATGCATTAGTACTAGTATATG"
        "TATTATCACCATTCATTTATATTAACCTTAAAGCAAGTACTAACGTTTAAGACGTACATAAACCAAATAT"
        "TTAAAATTCACAATTAATTTATTTAAACCTGAGAAAAGAGTTGTTCCACTATAATTGGTTCTCAAATATTT"
        "CCTTGAAATATTAACTTCTATTTAATTTAACTATATTAATGTAGTAAGAAACCACCTACTGGTTTATATTA"
        "AGGTATTCTATTCATGATAAGATCAGGGACAATAATCGTGGGGGTGGCGCAGAATGAACTATTACTTG"
        "CATTTGGCTTGGAATCTCACGGACATGACTGTAAAATTCCACCCTCCATACATTATATCTGGCATCTGG"
        "TTAAATGATGTGAGTACATACTCCTCATTAACCCCACATGCCGAGCATTCTTTTATATGCATAGGGGTTC"
        "TCCTTTTGGTTACCTTTCATCTTGCATATCAGAGTGCAGGCTCAAATGATAAATTAAGGTTGAACATATT"
        "CCTTGCTTAAGTTAAAGTAGGTTAATTATTGAAAGACATAACTTAAGAATTACATATTTTTAATTCAAGT"
        "GCATAACATATTATTCTTTCTTCAACTTACCCTTATATATATGCCCCCCTTTCGGTTTCTGCGCGACAAA"
        "CCCCCTTACCCCCTACGCTCAACAAATCCTGTTATCCTTGTCAAACCCCAAAACCAAGGAAGGTTCGA"
        "GAACGTGCAAGCTAACAAGTTGAAATATGAGTTAGCTATCCGCATTATATATATATATATACATACACAT"
        "CGCGTCAATTCGCCACATAATTCCCCAAATATAAACCTAAAAATTCCTATTAAATTTTAAGGGGCACGC"
        "CCCAATGCTAAAAAGTCCAACATTAAATAACGCTAGCGTAG"
    ),
    "Grass Carp": (
        "GACATTGCTACCCTCTATCTTGTATTTGGTGCCTGAGCCGGAATAGTGGGAACCGCTCTAAGCCTTCTC"
        "ATTCGAGCCGAACTAAGCCAACCCGGATCACTTCTGGGCGATGATCAAATTTATAATGTTATTGTCACT"
        "GCCCATGCCTTCGTAATAATTTTCTTTATAGTAATACCAATTCTTATTGGAGGGTTTGGAAATTGACTCG"
        "TACCATTAATAATTGGAGCACCCGACATAGCATTCCCACGAATAAACAACATGAGTTTCTGACTTCTAC"
        "CCCCTTCTTTCCTCCTACTATTAGCCTCTTCTGGTGTTGAGGCCGGAGCTGGAACAGGGTGAACAGTT"
        "TACCCACCACTCGCAGGCAATCTTGCCCACGCAGGAGCATCCGTAGACCTAACAATTTTCTCACTCCA"
        "CCTGGCAGGTGTGTCATCAATTTTAGGGGCAATTAATTTTATTACTACAACCATTAACATGAAACCACC"
        "AGCCATCTCCCAATACCAAACACCTCTCTTCGTTTGAGCTGTACTTGTAACAGCTGTACTCCTTCTTCTA"
        "TCTCTACCAGTTCTAGCCGCCGGAATTACAATACTCCTAACAGACCGTAATCTTAACACTACATTCTTT"
        "GACCCGGCGGGAGGAGGAGACCCAATTCTTTATCAACACTTATTCTGATTCTTTGGTCACCCGGAAGT"
        "TTATATTCTTATTTTACCCGGATTTGGAATCATTTCACATGTTGTAGCCTACTATGCAGGTAAAAAAGAA"
        "CCATTCGGTTATATAGGAATAGTCTGAGCTATAATGGCTATTGGTCTTCTAGGGTTTATTGTATGAGCCC"
        "ACCATATGTTTACTGTTGGGATAGACGTAGACACTCGTGCATATTTTACATCCGCAACGATAATTATTG"
        "CTATCCCAACAGGTGTAAAAGTATTTAGCTGACTAGCCACAC"
    ),
    "Black Carp": (
        "GACATTGGTACCCTTTATCTTGTATTTGGTGCCTGAGCCGGAATAGTGGGAACCGCTCTAAGCCTTCTC"
        "ATTCGAGCCGAACTAAGCCAACCCGGATCACTTCTGGGCGATGACCAAATTTATAATGTTATTGTCAC"
        "TGCCCATGCCTTCGTAATAATTTTCTTTATAGTAATACCAATTCTTATTGGAGGATTCGGAAACTGACTC"
        "GTACCGCTAATAATTGGAGCACCTGATATAGCATTCCCCCGAATGAATAACATAAGCTTCTGACTTCTG"
        "CCCCCATCTTTCCTCCTACTACTAGCCTCTTCTGGTGTTGAAGCTGGGGCTGGGACAGGGTGAACAGT"
        "CTACCCACCACTCGCAGGCAATCTTGCACACGCAGGAGCATCTGTAGATCTAACAATCTTTTCGCTAC"
        "ACCTGGCAGGTGTGTCATCAATTTTAGGAGCGATTAACTTCATCACTACAACTATCAACATAAAACCCC"
        "CAGCCATTTCTCAATACCAAACACCTCTCTTTGTCTGAGCTGTGCTAGTAACAGCCGTACTCCTTCTCC"
        "TATCCCTACCAGTCCTAGCTGCTGGAATTACAATACTCCTTACAGACCGTAACCTTAACACCACGTTCT"
        "TTGACCCAGCAGGCGGAGGAGACCCAATCCTATATCAACACCTGTTCTGATTCTTCGGCCACCCAGA"
        "AGTTTACATTCTTATTTTACCCGGGTTTGGGATCATTTCACACGTCGTAGCCTACTACGCGGGCAAAAA"
        "AGAACCATTTGGTTACATAGGAATGGTTTGAGCCATGATGGCTATTGGTCTCCTAGGATTTATTGTGTG"
        "AGCCCACCACATGTTTACTGTCGGAATAGACGTAGACACTCGTGCATACTTTACATCCGCAACAATAA"
        "TTATTGCTATCCCAACAGGTGTAAAAGTGTTTAGCTGACTAGCC"
    )
}


def detect_carp_species(query_seq, ref_dict, threshold=0.90):
    """
    Compare a query sequence to reference sequences for each carp species.
    Returns the species with the highest percent score above the threshold
    or None if no species passes the threshold.

    Args:
        query_seq (str): The eDNA sequence to identify.
        ref_dict (dict): A dictionary of {species_name: reference_sequence}.
        threshold (float): The minimum fraction of the maximum possible score required.
                           (Default: 0.90)

    Returns:
        (species, percent_score) or (None, percent_score) if no good match.
    """
    best_species = None
    best_percent = 0.0

    for species, ref in ref_dict.items():
        # Use local alignment (Smith-Waterman) for flexibility in matching.
        alignments = pairwise2.align.localms(query_seq, ref, 2, -1, -0.5, -0.1)
        if not alignments:
            continue
        best_alignment = alignments[0]  # best alignment
        score = best_alignment[2]
        # Calculate the maximum possible score if the entire ref is matched perfectly.
        max_possible = len(ref) * 2  # since match score is +2
        percent_similarity = score / max_possible

        print(f"Species: {species} | Alignment Score: {score:.2f} | Percent Similarity: {percent_similarity:.2%}")

        if percent_similarity > best_percent:
            best_percent = percent_similarity
            best_species = species

    if best_species and best_percent >= threshold:
        return best_species, best_percent
    else:
        return None, best_percent


if __name__ == "__main__":
    # In a typical Windows environment, you might load the query sequence from a file
    # or another source. For demonstration, we define one here directly.
    # Replace or modify this as needed.
    parser=argparse.ArgumentParser(description="Detect Carp Species from eDNA sequence or image.")
    parser.add_argument("--image", type=str, help="Path to image containing eDNA sequence.")
    parser.add_argument("--sequence", type=str, help="Directly input eDNA sequence as a string.")
    parser.add_argument("--threshold", type=float, default=0.85, help="Similarity threshold for species detection (default: 0.85).")
    parser.add_argument("--pdf", type=str, help="Path to PDF file containing eDNA sequence.")
    parser.add_argument("--sample", type=int, help="Specific sample number to analyze (for PDFs with multiple samples).")
    
    args= parser.parse_args()   

    if args.image:
        if not os.path.exists(args.image):
            print(f"Image file {args.image} does not exist.")
            exit(1)
        print(f"Processing image: {args.image}")
        
        # Check if image has multiple sequences
        sequences = extract_sequences_from_image(args.image)
        if len(sequences) > 1:
            print(f"Found {len(sequences)} sequences in image")
            results = analyze_multiple_sequences(sequences, ref_sequences, args.threshold)
        else:
            query_eDNA = extract_dna_from_image(args.image)
            species, similarity = detect_carp_species(query_eDNA, ref_sequences, args.threshold)
            if species:
                print(f"\nDetected species: {species} (Similarity: {similarity:.2%})")
            else:
                print(f"\nNo species detected with a similarity above the threshold. Best similarity was {similarity:.2%}.")
    
    elif args.sequence:
        query_eDNA = args.sequence.strip().upper()
        print(f"Using provided eDNA sequence of length {len(query_eDNA)}.")
        species, similarity = detect_carp_species(query_eDNA, ref_sequences, args.threshold)
        if species:
            print(f"\nDetected species: {species} (Similarity: {similarity:.2%})")
        else:
            print(f"\nNo species detected with a similarity above the threshold. Best similarity was {similarity:.2%}.")
    
    elif args.pdf:
        if not os.path.exists(args.pdf):
            print(f"PDF file {args.pdf} does not exist.")
            exit(1)
        print(f"Processing PDF: {args.pdf}")
        
        sequences = extract_dna_from_pdf(args.pdf)
        
        if not sequences:
            print("No DNA sequences found in PDF.")
            exit(1)
        
        if args.sample:
            # Analyze specific sample
            if args.sample in sequences:
                query_eDNA = sequences[args.sample]
                print(f"\nAnalyzing Sample {args.sample} (length: {len(query_eDNA)})")
                species, similarity = detect_carp_species(query_eDNA, ref_sequences, args.threshold)
                if species:
                    print(f"Sample {args.sample}: Detected {species} (Similarity: {similarity:.2%})")
                else:
                    print(f"Sample {args.sample}: No species detected above threshold. Best similarity: {similarity:.2%}")
            else:
                print(f"Sample {args.sample} not found. Available samples: {list(sequences.keys())}")

        else:
            # Analyze all samples
            results = analyze_multiple_sequences(sequences, ref_sequences, args.threshold)
            
            # Print summary
            print(f"\n=== SUMMARY ===")
            for sample_id, (species, similarity, status) in results.items():
                if species:
                    print(f"Sample {sample_id}: {species} ({similarity:.2%})")
                else:
                    print(f"Sample {sample_id}: No match ({similarity:.2%})")

    else:
        query_eDNA = (
            """
            GACATTTGGAGATTAAATATTGTGTGGGCGTGCACTGCGCTGACGAATACTTCGATGTTGGTGTTGAG
            TTTGATTACGTTGACTGCTGCCAAGGATAAGATGTTGGATACATTCGAATTGGAATATTATCGGTGGGC
            ATTTACTACCTCCACCACATTTAAGTTGAGAGTAATATTGCGGTGCAGGTGGTCCTTATTTACAACGGG
            ATAGGTGGAGAAGACATCGACATATGTCGCTAGATGGGATAGTTCTAATAAGAAGGAGGCTGAGTTT
            AATACCGCGAAAACGCGGGACTGCATGACTTATATGTTATCCACCCGTGAGTAAAGCACAAATATTTA
            GATGAGCACTTGCCGATTTGGGAGTGGCGAGGGCCGCTTGCACTTCCAAGACGCCCAATTCTGTGAA
            CTTGGTGTAGGTCACTTCAATGAACTTAATTTCCAGTATGGTGCCCTCAGCATTAAAGGGAGAAGCGG
            AAAAAACAATTAGGGCCGGATAGAGGCGTATGCTTTAGCTTGGTCGAAGAAGGGGTGGGAGACGAA
            GATTAAGGTGGAGGCCACCAGGTCCAAATGCATGTCGATTCTGAAGAAGGCCACTGGGATTTCCCGG
            GCCCAGTAGGGTATATCGTCGACTTGATGATCTCCCTACCAAGCCGGGCACTTAGCAGCCTGAGGCC
            GTGTTGACCAGGGAGGCGCGCACTTTATTATAGCGGGATGCGTCCATTGCAGAGACTAGGTTTTTCAA
            GCAAGAATAGAACTGGTGCATGGTGCTTGCTACCCTCTATCTTGTATTTTTAGTGGGTTGTTGATGATG
            ACTTGTGGTGCCGCGGCAACTGCCCCTGCCCATACCCGCAATACGTGATTTATTATTGACCAGGTAGT
            GGTTGGGGGATACGACCTCCAGGCATACCAAGGCGTTGC"""
        )

    # species, similarity = detect_carp_species(query_eDNA, ref_sequences, threshold=0.85)
    # if species:
    #     print(f"\nDetected species: {species} (Similarity: {similarity:.2%})")
    # else:
    #     print(f"\nNo species detected with a similarity above the threshold. Best similarity was {similarity:.2%}.")
