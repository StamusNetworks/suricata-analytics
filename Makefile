NOTEBOOKS = $(shell find ./jupyter/Notebooks/ -type f -name *.ipynb)

clean:
	jupyter nbconvert --clear-output --inplace $(NOTEBOOKS)
