# ccpdv2

scripts for testing HV2FEI4 v2

## Installation

### Install basil and pybar

- basil: https://github.com/SiLab-Bonn/basil 
  - rev 1011 14:59:07, Montag, 27. April 2015
  - branch development
- pybar: https://github.com/SiLab-Bonn/pyBAR
  - rev 2627 12:00:15, Mittwoch, 22. April 2015
  - branch development

### Get a copy of ccpdv2

ccpdv2: https://github.com/SiLab-Bonn/ccpdv2

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

## Quick start

- execute ipython.bat or ipython.sh
- import ccpdv2, make an instance of ccpdv2.Ccpdv2Fei4, and initialize
```python
   import ccpdv2
   c=ccpdv2.Ccpdv2Fei4()
   c.init_with_fei4()
```
- set parameters
all parameters can be set by the function "set()"
```python
   c.set(VNCOut0=0,th=0.9....)
```
- switch FEI4 readout ON/OFF
```python
   c.set(mode="hitmon")
```
    - mode="ccpd"
      - FEI4 readout : OFF
      - TDC of Monitor of ccpd : ON
    - mode="rj45"
      - FEI4 readout : OFF
      - TDC of Monitor of ccpd : ON
      - External trigger of FEI4 : TLU(RJ45 connector) or LEMO
    - mode="inj" :
      - FEI4 readout : OFF
      - TDC of Monitor of ccpd : OFF
      - External trigger of FEI4 : injection of ccpd (INJECTION of GPAC)
    - mode="hitmon" :
      - FEI4 readout : OFF
      - TDC of Monitor of ccpd : OFF
      - External trigger of FEI4 : HIT_OR of FEI4
- find noise edge
```python
   c.find_noise()
```
- tune tdac
```python
   c.find_tdac()
```
- check present status
```python
   c.show()
   ## or
   c.show2()
```
- tune fei4
```python
   c.run_fei4scan("tune")
```
