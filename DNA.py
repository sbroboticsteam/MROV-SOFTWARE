UnknownDNA={}
known_species = {}
count=0
k=int(input("Enter the value of k: "))
while True:

    Unknown_species=input("Enter the eDNA sequence of the unknown species: ")
    count+=1
    UnknownDNA[count]=Unknown_species
    choice=input("Do you want to enter another sequence? (y/n): ")
    if choice not in ['y','Y']:
        break
    

print("The eDNA sequences of the unknown species are:")
for i in UnknownDNA:
    print("Unknown sample",i,":",UnknownDNA[i])

while True:

    species_name = input("Enter species name: ")
    species_sequence = input(f"Enter DNA sequence for {species_name}: ").upper()
    known_species[species_name] = species_sequence
    choice = input("Do you want to enter another species? (y/n): ")
    if choice not in ['y','Y']:
        break
def hash_dna_sequence(sequence):
   
    return hash(sequence)
def find_best_match(unknown_dna, known_species):
    best_match = None
    max_score = 0
    unknown_hash = hash_dna_sequence(unknown_dna)

    for species, sequence in known_species.items():
        species_hash = hash_dna_sequence(sequence)
        # If hashes match, it's an exact match
        if unknown_hash == species_hash:
            best_match = species
            break

    return best_match

# Matching Unknown DNA to Known Species using Hashing
print("\nMatching unknown eDNA sequences to known species...")
for sample_id, unknown_seq in UnknownDNA.items():
    best_match = find_best_match(unknown_seq, known_species)
    if best_match:
        print(f"Unknown sample {sample_id} matches exactly with: {best_match}")
    else:
        print(f"Unknown sample {sample_id} has no exact match.")
