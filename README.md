===============================================
ccpdv2
===============================================
scripts for testing HV2FEI4 v2

Installation
=============
Install basil and pybar. Then, get a copy of ccpdv2
-basile: https://github.com/SiLab-Bonn/basil
-pybar: https://github.com/SiLab-Bonn/pyBAR

Quick start
=============
-execute ipython.bat or ipython.sh
-import ccpdv2, make a instace of ccpdv2.Ccpdv2Fei4, and initiarize
```python
   import ccpdv2
   c=ccpdv2.Ccpdv2Fei4()
   c.init_with_fei4()
```
-set parameters
```python
   c.set(VNCOut0=0,th=0.9....)
```
-switch to FEI4(HITOR for external trigger)
```python
   c.set(mode="hitmon")
```
-switch off FEI4 and read with Monitor
```python
   c.set(mode="ccpd")
```
-find noise
```python
   c.find_noise()
```
-tune tdac
```python
   c.find_tdac()
```