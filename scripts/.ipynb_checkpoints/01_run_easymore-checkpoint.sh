#!/bin/bash
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --time=0-7:00:00
#SBATCH --mem=48G
#SBATCH --job-name=easymore
#SBATCH --error=slurm_logs/slurm_%j.err
#SBATCH --output=slurm_logs/slurm_%j.out
#SBATCH --array=1-25

# Add the directory where the modules are located to the MODULEPATH
. /work/comphyd_lab/local/modules/spack/2024v5/lmod-init-bash # if you're using zsh, change bash with zsh
module unuse $MODULEPATH
module use /work/comphyd_lab/local/modules/spack/2024v5/modules/linux-rocky8-x86_64/Core/

# Restore modules from the scimods collection
module restore scimods

source ~/virtual-envs/scienv/bin/activate

directory_index=$SLURM_ARRAY_TASK_ID
ensembles=3
range=$((directory_index * ensembles - ensembles))

for ((i = $range; i < $((range + ensembles)); i++)); do
    python 01_run_easymore.py "$i"
done




