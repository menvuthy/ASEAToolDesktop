import ee
ee.Initialize()


####################### Shoreline Analysis Parameters #################

# 1. Define the area of interest
'''Note: always change from null to None, and false to False'''
aoi =  ee.Geometry.Polygon(
        [[[73.50008101775114, 1.95254395086047],
          [73.50008101775114, 1.8489175407075442],
          [73.57269378020231, 1.8489175407075442],
          [73.57269378020231, 1.95254395086047]]], None, False);


# 2. Define start date and end date
date = ['2023-01-01', '2023-12-31']

# 3. Georeferencing
horizontal_step = 0     # (+ Positive) Move to right // (- Negative) Move to left
vertical_step = 0       # (+ Positive) Move to top // (- Negative) Move to bottom

########################################################################