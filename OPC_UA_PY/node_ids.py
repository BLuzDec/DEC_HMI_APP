Node_id_test_lab = {
    # 'Dose_number': 'ns=4;i=3',
    'PressureSensor': 'ns=4;i=4',
    'FlowSensor': 'ns=4;i=5',
}

Node_id_flexpts_S7_1200 = {
    'Dose_number': 'ns=4;i=3',
    'StableWeight': 'ns=4;i=4',
    'TargetWeight': 'ns=4;i=5',
    'EjectorPosition': 'ns=4;i=6',
    'InstantDensity': 'ns=4;i=7',
    'AvgDensity': 'ns=4;i=8',
    'DB_Logs_uPTS_FT': 'ns=4;i=9',
    'Vacuum_P1': 'ns=4;i=10',
    'Vacuum_time': 'ns=4;i=2',
    'High_pressure_time': 'ns=4;i=11',
    'High_pressure': 'ns=4;i=12',
}

Node_id_flexpts_S7_1500 = {
    'Dose_number': 'ns=4;i=3',
    'TargetWeight': 'ns=4;i=4',
    'StableWeight': 'ns=4;i=5',
    'EjectorPosition': 'ns=4;i=6',
    'InstantDensity': 'ns=4;i=7',
    'AvgDensity': 'ns=4;i=8',
    'rTimerSuction': 'ns=4;i=9',
    'rTimerEjection1': 'ns=4;i=10',
    'rTimerEjection2': 'ns=4;i=11',
    'rTimerVibrator': 'ns=4;i=12',
    'rEjectingPressure1': 'ns=4;i=13',
    'rEjectingPressure2': 'ns=4;i=14',
    'rUncloggingPressure': 'ns=4;i=15',
    'rVacuumPressure1': 'ns=4;i=16',
    'rVacuumPressure2': 'ns=4;i=17',
    'rDelayAlternateVacuum': 'ns=4;i=18',
    'rDelayCloseOutletValve': 'ns=4;i=19',
    'rDelaySetEjectingPressure1': 'ns=4;i=20',
    'rDelayVibrator': 'ns=4;i=21',
    'rDelayAtmPressure': 'ns=4;i=22',
    'rVibratorPressure': 'ns=4;i=23',
}


DataBlock = 20
Node_id_flexpts_S7_1500_snap7 = {
    'Dose_number': (DataBlock, 0, 'INT'),        # DB20.DBW0
    'StableWeight': (DataBlock, 2, 'REAL'),     # DB20.DBD2
    'TargetWeight': (DataBlock, 6, 'REAL'),     # DB20.DBD6
    'EjectorPosition': (DataBlock, 10, 'REAL'), # DB20.DBD10
    'InstantDensity': (DataBlock, 14, 'REAL'),  # DB20.DBD14
    'AvgDensity': (DataBlock, 18, 'REAL'),      # DB20.DBD18
    'rEjectingPressure1': (DataBlock, 22, 'REAL'), # DB20.DBD22
    'rTimerEjection1': (DataBlock, 26, 'REAL'),    # DB20.DBD26
    'rEjectingPressure2': (DataBlock, 30, 'REAL'), # DB20.DBD30
    'rTimerEjection2': (DataBlock, 34, 'REAL'),    # DB20.DBD34
    'rUncloggingPressure': (DataBlock, 38, 'REAL'),# DB20.DBD38
    'rVacuumPressure1': (DataBlock, 42, 'REAL'),   # DB20.DBD42
    'rTimerSuction': (DataBlock, 46, 'REAL'),      # DB20.DBD46
    'rVacuumPressure2': (DataBlock, 50, 'REAL'),   # DB20.DBD50
    'rDelayAlternateVacuum': (DataBlock, 54, 'REAL'), # DB20.DBD54
    'rDelayCloseOutletValve': (DataBlock, 58, 'REAL'), # DB20.DBD58
    'rDelaySetEjectingPressure1': (DataBlock, 62, 'REAL'), # DB20.DBD62
    'rVibratorPressure': (DataBlock, 66, 'REAL'),  # DB20.DBD66
    'rTimerVibrator': (DataBlock, 70, 'REAL'),     # DB20.DBD70
    'rDelayVibrator': (DataBlock, 74, 'REAL'),     # DB20.DBD74
    'rDelayAtmPressure': (DataBlock, 78, 'REAL'),  # DB20.DBD78
    # Pressure variables for high-frequency logging
    'FlexPTS_running': (DataBlock, 82, 'BOOL'),    # DB20.DBX82.0
    'PT_Chamber': (DataBlock, 84, 'REAL'),         # DB20.DBD84
    'PR_Chamber': (DataBlock, 88, 'REAL'),         # DB20.DBD88
    'PT_Outlet': (DataBlock, 92, 'REAL'),          # DB20.DBD92
    'PR_Outlet': (DataBlock, 96, 'REAL'),          # DB20.DBD96
    
    # PT_Chamber array for high-frequency data (50 values)
    'PT_Chamber_Array': (DataBlock, 100, 'REAL', 600),  # DB20.DBD100 to DB20.DBD156 (60 * 4 bytes each)
    'PR_Chamber_Array': (DataBlock, 2504, 'REAL', 600),  # DB20.DBD500 to DB20.DBD556 (60 * 4 bytes each)
}

Node_id_micropts = {
    'Dose_number': 'ns=4;i=14',
    'StableWeight': 'ns=4;i=15',
    'TargetWeight': 'ns=4;i=9',
    'EjectorPosition': 'ns=4;i=10',
    'InstantDensity': 'ns=4;i=11',
    'AvgDensity': 'ns=4;i=12',
    'DB_Logs_uPTS_FT': 'ns=4;i=13',
    'Vacuum_P1': 'ns=4;i=19',
    'Vacuum_time': 'ns=4;i=20',
    'High_pressure_time': 'ns=4;i=21',
    'High_pressure': 'ns=4;i=22',
    'Ejector_Force_of_Compression': 'ns=4;i=23',
}

Node_id_FlexPTS_Simulation = {
    'Dose_number': 'ns=5;i=2',
    'StableWeight': 'ns=5;i=3',
    'TargetWeight': 'ns=5;i=4',
    'EjectorPosition': 'ns=5;i=5',
    'InstantDensity': 'ns=5;i=6',
    'AvgDensity': 'ns=5;i=7',
    #-------------------------------- FlexPTS In/Out
    'rPressureOutletVvibration': 'ns=5;i=8',
    'rVibratorPressure': 'ns=5;i=9',
    'bCylinderMoveDone': 'ns=5;i=10',
    'iInletValvePressure': 'ns=5;i=11',
    'iOutletValvePressure': 'ns=5;i=12',
    'bStart_Stop_Operator': 'ns=5;i=13',
    'iChamberPressure': 'ns=5;i=14',
    'oInletValve': 'ns=5;i=15',
    'oOutletValve': 'ns=5;i=16',
    'oChamberPressure': 'ns=5;i=17',
    'bAgitatorHopperRight': 'ns=5;i=18',
    'bAgitatorHopperLeft': 'ns=5;i=19',
    'bDone': 'ns=5;i=20',
    #-------------------------------- Recipes
    # Parameters
    'rInletClosePressure': 'ns=5;i=21',
    'rInletPreVacuumPressure': 'ns=5;i=22',
    'rOutletClosePressure': 'ns=5;i=23',
    'rVacuumPressure1': 'ns=5;i=24',
    'rVacuumPressure2': 'ns=5;i=25',
    'rEjectingPressure1': 'ns=5;i=26',
    'rEjectingPressure2': 'ns=5;i=27',
    'rUncloggingPressure': 'ns=5;i=28',
    'rPreVacuumPressure': 'ns=5;i=29',
    # Timers
    'rTimerSuction': 'ns=5;i=30',
    'rTimerEjection1': 'ns=5;i=31',
    'rTimerEjection2': 'ns=5;i=32',
    'rTimerUncloggingPressure': 'ns=5;i=33',
    'rDelayOpenInletValve': 'ns=5;i=34',
    'rDelayPreVacuumValves': 'ns=5;i=35',
    'rDelayCloseInletValve': 'ns=5;i=36',
    'rDelayAlternateVacuum': 'ns=5;i=37',
    'rDelayAtmPressure': 'ns=5;i=38',
    'rDelayOpenOutletValve': 'ns=5;i=39',
    'rDelaySetEjectingPressure1': 'ns=5;i=40',
    'rDelayCloseOutletValve': 'ns=5;i=41',
    'rDelayCylinderMove': 'ns=5;i=42',
    'rHopperRotationTime': 'ns=5;i=43',
    'rTimerPreVacuum': 'ns=5;i=44',
    'rDelayCloseInletOutletValve': 'ns=5;i=45',
    'rVibrationFrequency': 'ns=5;i=46',
    'rDelayStartOutletVibration': 'ns=5;i=47',
    'rDelayVibrator': 'ns=5;i=48',
    'rTimerVibrator': 'ns=5;i=49',
    # Settings
    'bUseInletPinchValve': 'ns=5;i=50',
    'bDoubleVacuum': 'ns=5;i=51',
    'bVialPreVacuum': 'ns=5;i=52',
    'bCalibrationOk': 'ns=5;i=53',
    'bAirSupply': 'ns=5;i=54',
    'bUsePressureRegulationFeedback': 'ns=5;i=55',
    'bManualRequestDischarge': 'ns=5;i=56',
    'bOutlet_Vibration': 'ns=5;i=57',
    'bCylinderMove': 'ns=5;i=58',
    # Others
    'nNumForAnAverage': 'ns=5;i=59',
    'rStarting_Density': 'ns=5;i=60',
    'rTolerance': 'ns=5;i=61',
    'rChamberDiameter': 'ns=5;i=62',
    'rDead_volume': 'ns=5;i=63',
    'rChamberHeightMax': 'ns=5;i=64',
    'rChamberHeightMin': 'ns=5;i=65',
    'byLinMotorForce': 'ns=5;i=66',
    'rMotorEndStopOffset': 'ns=5;i=67',
    'rPressureOutletVvibration': 'ns=5;i=68',
    'rVibratorPressure': 'ns=5;i=69',
}
