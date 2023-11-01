import os
import glob
import natsort
import rasterio
from rasterio.plot import show
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib_scalebar.scalebar import ScaleBar
from matplotlib.patches import Patch
from shapely.ops import unary_union
from codes.shoreline import Create_points, ExtrapolateOut, ExtrapolateIn
from codes.shoreline import create_union_polygon, create_shoreline_change_points
from codes.shoreline import merge_shoreline_change, linearring_to_polygon
from shapely.geometry import MultiPolygon, Polygon
from parameters import aoi, date
from matplotlib import rcParams
plt.rcParams['font.family'] =  ['serif']
rcParams['font.stretch'] = 'extra-condensed'
import warnings
warnings.filterwarnings("ignore")

# Create folder
if not os.path.exists('output/shoreline/retreat&growth'):
  os.makedirs('output/shoreline/retreat&growth')
  
if not os.path.exists('output/shoreline/shoreline-change'):
  os.makedirs('output/shoreline/shoreline-change')

if not os.path.exists('output/shoreline/union-shoreline'):
  os.makedirs('output/shoreline/union-shoreline')

# File and folder paths
file_path = "input/shoreline"

# Make a search criteria to select the ndvi files
q = os.path.join(file_path, "shoreline_*.json")

shoreline_fp = natsort.natsorted(glob.glob(q)) # sorted files by name

# Import shoreline data
shl_past = gpd.read_file(shoreline_fp[0]).dropna().reset_index(drop=True)
shl_present = gpd.read_file(shoreline_fp[-1]).dropna().reset_index(drop=True)

# Convert LinearRing to Polygon
shl_past = linearring_to_polygon(shl_past)
shl_present = linearring_to_polygon(shl_present)

# Calculate growth and retreat
retreat = gpd.overlay(shl_past, shl_present, how='difference', keep_geom_type=False)
growth = gpd.overlay(shl_present, shl_past, how='difference', keep_geom_type=False)

# Export growth and retreat geometry to GeoJSON
retreat.to_file('output/shoreline/retreat&growth/retreat.json', driver='GeoJSON')
growth.to_file('output/shoreline/retreat&growth/growth.json', driver='GeoJSON')

# Create union polygon from geodata of growth area 
growth_poly = create_union_polygon(growth)

# Create union polygon from geodata of retreat area 
retreat_poly = create_union_polygon(retreat)

# Create shoreline change as points along shoreline
growth_shoreline_change = create_shoreline_change_points(shl_present, growth_poly)
retreat_shoreline_change = create_shoreline_change_points(shl_present, retreat_poly)

# Export shoreline growth and retreat to GeoJSON
growth_shoreline_change.to_file('output/shoreline/retreat&growth/growth_points.json', driver='GeoJSON')
retreat_shoreline_change.to_file('output/shoreline/retreat&growth/retreat_points.json', driver='GeoJSON')


# Calculate total year
total_year = int(shoreline_fp[-1][-18:-14]) - int(shoreline_fp[0][-18:-14]) + 1

# Create shoreline change
change_distance = merge_shoreline_change(growth_shoreline_change, retreat_shoreline_change)
shoreline_change = retreat_shoreline_change.drop(columns=['change_m'])
shoreline_change['total change_m'] = change_distance
shoreline_change['rate per year_m'] = (shoreline_change['total change_m']/total_year).round(2)

# Export shoreline change to GeoJSON
shoreline_change.to_file('output/shoreline/shoreline-change/shoreline_change.json', driver='GeoJSON')

# Create a combination of all shorelines
shape_list = []
for i in range(len(shoreline_fp)):
  shoreline = gpd.read_file(shoreline_fp[i]).dropna().reset_index(drop=True)
  for n in range(len(shoreline)):
    try:
        shoreline = linearring_to_polygon(shoreline.iloc[n:n+1,:])
    except:
        pass
  for k in range(len(shoreline)):
    if type(shoreline['geometry'][k]) == MultiPolygon:
      polygons = list(shoreline['geometry'][k].geoms)
      shoreline.at[k,'geometry'] = polygons[0]
  geo_shoreline = unary_union(shoreline['geometry'].exterior)
  shape_list.append(geo_shoreline)

# Create a list of shoreline year
year = []
for name in shoreline_fp:
  year.append(name[-18:-5])

# Export union shoreline to GeoJSON
geo_shoreline = gpd.GeoDataFrame({'geometry':shape_list}, crs=shl_present.crs)
geo_shoreline['id'] = geo_shoreline.index
geo_shoreline['year'] = year
geo_shoreline.to_file('output/shoreline/union-shoreline/union_shoreline.json', driver='GeoJSON')


# Read input image data
Image = rasterio.open('output/satellite-image/post-processed-images/image_snrgb_2m_'+shoreline_fp[-1][-18:-5]+'.tif')
Rescaled_img = Image.read()
transform = Image.transform

# Read bands
swir1 = Rescaled_img[0]
nir = Rescaled_img[1]
red = Rescaled_img[2]
green = Rescaled_img[3]
blue = Rescaled_img[4]

# Create SNB composite
RGB = np.dstack((red, green, blue))

# adjust the contrast and brightness settings
alpha = 3  # controls the contrast
beta = 0.05    # controls the brightness
image = np.clip(alpha * RGB + beta, 0, 1)
RGB_transp = image.transpose(2, 0, 1)

# Create plot
fig, ax = plt.subplots(figsize=(7,7))
show(RGB_transp, ax=ax, transform=transform)
growth.plot(ax=ax, facecolor='blue')
retreat.plot(ax=ax, facecolor='red')
ax.add_artist(ScaleBar(1, location='lower left', box_alpha=0.5, font_properties={'size': 'small'}))
# Add legend
plt.legend(loc='upper left', handles=[Patch(color='blue', label='Accumulation'),
                        Patch(color='red', label='Erosion')], fontsize='small')

plt.title(shoreline_fp[0][-18:-5]+' - '+shoreline_fp[-1][-18:-5], fontsize=12)
plt.tight_layout()
plt.savefig('output/shoreline/figure/growth&retreat_'+shoreline_fp[-1][-18:-5]+'.png', dpi=300)


# Create one subplot. Control figure size in here.
fig, ax = plt.subplots(figsize=(7,7))
show(RGB_transp, ax=ax, transform=transform)
geo_shoreline.plot(ax=ax,
          column="year",
          categorical=True,
          linewidth=1,
          cmap='magma',
          legend=True,
          legend_kwds={'loc': 'upper left', 'fontsize': 'small'},
          )
ax.add_artist(ScaleBar(1, location='lower left', box_alpha=0.5, font_properties={'size': 'small'}))
plt.title(shoreline_fp[0][-18:-5]+' - '+shoreline_fp[-1][-18:-5], fontsize=12)
plt.tight_layout()
plt.savefig('output/shoreline/figure/all_shorelines.png', dpi=300)

#---------------------------------------------------------------------
if shoreline_fp == []:
  print('Error: There is no shoreline for analysis, and there should be at least 2 shorelines for two different period.')
else:
  print('Shoreline analysis is finished!')


