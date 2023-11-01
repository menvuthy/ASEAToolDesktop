import os
import cv2
import folium
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
import geopandas as gpd
import shapely
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.geometry.polygon import LinearRing
import rasterio
from rasterio.plot import show
from rasterio.features import shapes
from rasterio.enums import Resampling
from rasterio.plot import show_hist
import matplotlib.pyplot as plt
from matplotlib_scalebar.scalebar import ScaleBar
from codes import shoreline, download, mapping
from codes.shoreline import Create_points
from parameters import aoi, date, horizontal_step, vertical_step
from shapely.ops import unary_union
from scipy import interpolate
from matplotlib import rcParams
plt.rcParams['font.family'] =  ['serif']
rcParams['font.stretch'] = 'extra-condensed'

import warnings
warnings.filterwarnings("ignore")

# Create folder
if not os.path.exists('output/satellite-image/post-processed-images'):
  os.makedirs('output/satellite-image/post-processed-images')
if not os.path.exists('output/shoreline/geojson'):
  os.makedirs('output/shoreline/geojson')
if not os.path.exists('output/shoreline/figure/shorelines'):
  os.makedirs('output/shoreline/figure/shorelines')

# Set date
start_date = date[0]
end_date = date[1]

# Create filename
start_yyyy = start_date[:4]
start_mm = start_date[5:7]
end_yyyy = end_date[:4]
end_mm = end_date[5:7]
file_name = start_yyyy+start_mm+'_'+end_yyyy+end_mm

# ------ Calculate EPSG ------ #
lon = aoi.geometries().getInfo()[0]['coordinates'][0][0][0]
lat = aoi.geometries().getInfo()[0]['coordinates'][0][0][1]
epsg_code = download.convert_wgs_to_utm(lon, lat)

# ------ Shoreline extraction ------ #
# Read input image data
Image = rasterio.open('output/satellite-image/pre-processed-images/image_snrgb_10m_'+file_name+'.tif')
if Image.read().any() == 0:
  print('Warning: The image is empty, so shoreline cannot be extracted.')

else:
  print('Extracting shoreline...')

rescale_image, transform = shoreline.resampling(image=Image, scale_factor=5)
      
# Georeference in Maldives
if epsg_code == str(32643):
  ncol = 4 - horizontal_step
  nrow = 1 + vertical_step
  buffer_rate = -5
elif epsg_code == str(32743):
  ncol = 4 - horizontal_step
  nrow = 2 + vertical_step
  buffer_rate = -5
else:
  ncol = -horizontal_step
  nrow = vertical_step
  buffer_rate = -15

# Slice column number
if ncol < 0:
  # Negative
  rescale_image = np.delete(rescale_image, np.s_[rescale_image.shape[2]-abs(ncol):rescale_image.shape[2]], axis=2)
  new_col = np.empty((rescale_image.shape[0],rescale_image.shape[1], abs(ncol)))
  new_col.fill(np.nan)
  rescale_image = np.array([np.c_[new_col[i], rescale_image[i]] for i in range(rescale_image.shape[0])])
else:
  # Positive
  rescale_image = np.delete(rescale_image, slice(0,ncol), axis=2)
  new_col = np.empty((rescale_image.shape[0],rescale_image.shape[1], ncol))
  new_col.fill(np.nan)
  rescale_image = np.c_[rescale_image, new_col]

# Slice row number
if nrow < 0:
  # Negative
  rescale_image = np.delete(rescale_image, np.s_[rescale_image.shape[1]-abs(nrow):rescale_image.shape[1]], axis=1)
  new_row = np.empty((rescale_image.shape[0], abs(nrow), rescale_image.shape[2]))
  new_row.fill(np.nan)
  rescale_image = np.array([np.r_[new_row[i], rescale_image[i]] for i in range(rescale_image.shape[0])])
else:
  # Positive
  rescale_image = np.delete(rescale_image, slice(0,abs(nrow)), axis=1)
  new_row = np.empty((rescale_image.shape[0], abs(nrow), rescale_image.shape[2]))
  new_row.fill(np.nan)
  rescale_image = np.array([np.r_[rescale_image[i], new_row[i]] for i in range(rescale_image.shape[0])])

# Set metadata
out_meta = Image.meta.copy()
out_meta.update({"driver": "GTiff",
                "dtype": "float32",
                "nodata": 0 and None,
                "height": rescale_image.shape[1],
                "width": rescale_image.shape[2],
                "transform": transform,
                "count": 5,
                "crs": Image.crs
                }
                )
# Write the clip raster
output = os.path.join('output/satellite-image/post-processed-images/image_snrgb_2m_'+file_name+'.tif')
with rasterio.open(output, "w", **out_meta) as dest:
    dest.write(rescale_image.astype(np.float32))

# Read bands
swir1 = rescale_image[0]
nir = rescale_image[1]
red = rescale_image[2]
green = rescale_image[3]
blue = rescale_image[4]

# Separate water and non-water by K-Means
Input_DF = pd.DataFrame({'nir':nir.reshape(-1)})

# Set X as input feature data
X_KMeans = Input_DF.dropna()

# Apply KMeans clustering
kmeans = KMeans(n_clusters=2, init='k-means++', max_iter=200, random_state=42)
Y_KMeans = kmeans.fit(X_KMeans)
# Assign label
X_group = X_KMeans.copy()
X_group['cluster_id'] = Y_KMeans.labels_


# Re-arrange cluster index
clust_kmean = pd.DataFrame()
clust_kmean['id'] = X_KMeans.index
clust_kmean['class'] = kmeans.labels_
indx = []
for i in range(len(Input_DF)):
    indx.append(i)
Index = pd.DataFrame()
Index['id'] = indx
df1 = Index.set_index('id')
df2 = clust_kmean.set_index('id')
df2 = clust_kmean.set_index(df2.index.astype('int64')).drop(columns=['id'])
mask = df2.index.isin(df1.index)
df1['cluster'] = df2.loc[mask, 'class']

# Reshape the cluster array
array = np.array(df1['cluster'])
n_array = array.reshape(nir.shape)

nir_max = np.where(nir == np.nanmax(nir)) 
if n_array[nir_max[0][0]][nir_max[1][0]] == 0:
  n_array2 = np.where(n_array==0, 255, n_array)
  mask = np.where(n_array2 == 1.0, np.nan, n_array2)
  mask = np.where(np.isnan(mask), 0, mask)
else:
  mask = np.where(n_array==1.0, 255, n_array)
  mask = np.where(np.isnan(mask), 0, mask)

# ------ Save result as GeoJSON file ------ #
# Export result
polygons = (
        {'properties': {'raster_val': v}, 'geometry': s}
        for i, (s, v) 
        in enumerate(
            shapes(mask.astype('uint8'), mask=None, transform=transform)))
geometry = list(polygons)

# Create new geodataframe
geom_dataframe  = gpd.GeoDataFrame.from_features(geometry)

# Set projection of dataframe
geom = geom_dataframe.set_crs(Image.crs)

# Remove no-data geometries
geom = geom[geom.raster_val != 0]

# Extract  boundaries
list_poly = []
for p in geom['geometry']:
  list_poly.append(Polygon(p.exterior))

smooth_poly = []
for i in range(len(list_poly)):
  poly_line = list_poly[i]
  outbuffer = poly_line.buffer(10, resolution=5, cap_style=1, join_style=1, mitre_limit=2, single_sided=True)
  inbuffer = outbuffer.buffer(-10.5, resolution=5, cap_style=1, join_style=1, mitre_limit=2, single_sided=True)
  simplified = inbuffer.simplify(1, preserve_topology=False) # False: Use Douglas-Peucker algorithm
  inbuffer2 = simplified.buffer(buffer_rate, resolution=5, cap_style=1, join_style=1, mitre_limit=2, single_sided=True)
  
  if type(inbuffer2) == MultiPolygon:
    ring = [LinearRing(inbuffer2.geoms[k].exterior) for k in range(len(inbuffer2.geoms))]
    ring = unary_union(ring)
    smooth_poly.append(ring)
  else:
    ring = LinearRing(inbuffer2.exterior)
    smooth_poly.append(ring)

# Remove empty ring
ring_list = []
for ring in smooth_poly:
    if not ring.is_empty:
        ring_list.append(ring)
        
# Create new geodataframe for exterior boundaries
geo_shoreline = gpd.GeoDataFrame({'geometry':ring_list}, crs=Image.crs)
geo_shoreline = geo_shoreline.dropna().reset_index(drop=True)
geo_shoreline['id'] = geo_shoreline.index

# Save to geojson file
outfp = 'output/shoreline/geojson/shoreline_'+file_name+'.json'
geo_shoreline.to_file(outfp, driver='GeoJSON')

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
geo_shoreline.plot(ax=ax, facecolor='None', edgecolor='yellow', linewidth=1, label='shoreline')
ax.add_artist(ScaleBar(1, location='lower left', box_alpha=0.5, font_properties={'size': 'small'}))
plt.title(start_date+' - '+end_date, fontsize=12)
plt.legend(loc='upper right')
plt.tight_layout()
plt.savefig('output/shoreline/figure/shorelines/shoreline_'+file_name+'.png', dpi=300)

#---------------------------------------------------------------------
print('Shoreline extraction completed!')