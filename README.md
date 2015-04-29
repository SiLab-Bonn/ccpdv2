#ccpdv2

scripts for testing HV2FEI4 v2

##Installation

### Install basil and pybar

- basile: https://github.com/SiLab-Bonn/basil 
  - rev 999 14:59:07, Montag, 27. April 2015
- pybar: https://github.com/SiLab-Bonn/pyBAR
  - rev 2627 12:00:15, Mittwoch, 22. April 2015

### Get a copy of ccpdv2

### Configure pybar

change configuration files
- configuration.yaml
```yaml
dut: <path to ccpdv2.yaml>
dut_configuration : dut_configuration_mio_gpac.yaml 
```
- dut_configuration_mio_gpac.yaml
```yaml
USB:
    bit_file       : "<path to ccpdv2.bit>"
```

##Quick start

- execute ipython.bat or ipython.sh
- import ccpdv2, make an instance of ccpdv2.Ccpdv2Fei4, and initialize
```python
   import ccpdv2
   c=ccpdv2.Ccpdv2Fei4()
   c.init_with_fei4()
```
- set parameters
```python
   c.set(VNCOut0=0,th=0.9....)
```
- switch to FEI4(HITOR for external trigger)
```python
   c.set(mode="hitmon")
```
- switch off FEI4 and read with Monitor
```python
   c.set(mode="ccpd")
```
- find noise
```python
   c.find_noise()
```
- tune tdac
```python
   c.find_tdac()
```